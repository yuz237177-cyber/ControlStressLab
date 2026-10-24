"""Load-delay protocol, physical reachability, pairing and preservation contracts."""

import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from archive_results import archive
from controlstresslab import DCMotor, PID, simulate
from controlstresslab.metrics import evaluate
from controlstresslab.stress_grid import StressPlan, cases, classify, execute_grid, required_voltage, summarize


class StressPlanChecks(unittest.TestCase):
    def test_domain_validation(self):
        for values in ((), (0, -1), (False,), (0, float("inf")), (0, float("nan")), (0, 0), (0.1,), (0, 0.2, 0.1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                StressPlan(loads_Nm=values)
        with self.assertRaises(ValueError):
            StressPlan(delays_s=(0, 0.015))
        with self.assertRaises(ValueError):
            StressPlan(event_s=0.5)
        with self.assertRaisesRegex(ValueError, "resource"):
            StressPlan(loads_Nm=tuple(range(501)), delays_s=(0, 0.01))

    def test_default_counts_include_baselines_once(self):
        self.assertEqual(StressPlan().expected_runs, 286)
        self.assertEqual(len(StressPlan().delays_s) * 2, 22)

    def test_required_voltage_and_exact_steady_limit(self):
        self.assertAlmostEqual(required_voltage(0, 60), 6.6)
        self.assertAlmostEqual(required_voltage(0.54, 60), 12)
        self.assertAlmostEqual(required_voltage(0.6, 60), 12.6)

    def test_classification_does_not_relabel_recovery_as_stability(self):
        metrics = {"status": "completed", "recovery_status": "recovered_in_observation_window"}
        self.assertEqual(classify(metrics, True), "recovered")
        self.assertEqual(classify(metrics, False), "steady_reference_infeasible")
        metrics["recovery_status"] = "not_recovered_in_observation_window"
        self.assertEqual(classify(metrics, True), "not_recovered_in_window")
        metrics["status"] = "numerical_failure"
        self.assertEqual(classify(metrics, False), "execution_or_metric_failure")


class StressCaseChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = StressPlan((0, 0.15, 0.6), (0, 0.1))
        cls.pairs = list(cases(cls.plan))

    def test_frozen_gains_and_no_hidden_parameter_scan(self):
        self.assertEqual(len(self.pairs), 12)
        self.assertEqual(len({r["case_id"] for r, _ in self.pairs}), 12)
        for record, run in self.pairs:
            self.assertEqual(tuple(record["controller"][key] for key in ("kp", "ki", "kd")), (0.25, 0.8, 0))
            self.assertEqual(record["plant"]["inertia_kg_m2"], 0.01)
            self.assertEqual(record["plant"]["friction_Nm_s"], 0.001)
            self.assertEqual(run.scenario.noise_std, 0)
            self.assertEqual(run.scenario.evaluation_start_s, 8)

    def test_load_event_and_delay_match_recorded_channels(self):
        record, run = next((r, run) for r, run in self.pairs if r["load_Nm"] == 0.15 and r["delay_s"] == 0.1 and r["controller_name"] == "pid")
        self.assertEqual(run.rows[799]["load_Nm"], 0)
        self.assertEqual(run.rows[800]["load_Nm"], 0.15)
        self.assertEqual(run.rows[100]["measurement_rad_s"], run.rows[90]["true_output_rad_s"])
        self.assertEqual(record["metrics"], evaluate(simulate(DCMotor(), PID(), self.plan.scenario(0.15, 0.1))))

    def test_zero_controls_and_paired_integral(self):
        for record, run in self.pairs:
            self.assertTrue(record["pre_event_pair_matches"])
            self.assertEqual(record["incremental_status"], "available")
            if record["load_Nm"] == 0:
                self.assertEqual(record["incremental_load_iae_rad"], 0)
            baseline = next(other for r, other in self.pairs if r["case_id"] == record["baseline_case_id"])
            expected = sum(abs(a["true_output_rad_s"] - b["true_output_rad_s"]) * a["interval_s"] for a, b in zip(run.rows, baseline.rows) if a["time_s"] >= 8 and a["interval_s"] > 0)
            self.assertAlmostEqual(record["incremental_load_iae_rad"], expected, places=12)

    def test_pre_event_settlement_and_outcomes_are_independent(self):
        for record, _ in self.pairs:
            self.assertTrue(record["pre_event_settled"])
            if record["load_Nm"] == 0.6:
                self.assertEqual(record["classification"], "steady_reference_infeasible")
                self.assertEqual(record["metrics"]["status"], "completed")
        groups = summarize([r for r, _ in self.pairs])
        self.assertEqual(groups[0]["steady_reference_infeasible"], 2)
        self.assertEqual(groups[0]["execution_or_metric_failure"], 0)

    def test_exact_reference_infeasible_can_still_enter_error_band(self):
        for record, _ in cases(StressPlan((0, 0.55), (0,))):
            if record["load_Nm"] == 0.55:
                self.assertFalse(record["steady_reference_feasible"])
                self.assertEqual(record["classification"], "steady_reference_infeasible")
                self.assertEqual(record["metrics"]["recovery_status"], "recovered_in_observation_window")


class StressExportChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "outputs").mkdir(exist_ok=True)

    def test_full_export_and_integrity(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary:
            output = Path(temporary) / "grid"
            execute_grid(output, StressPlan((0, 0.6), (0,)))
            manifest = json.loads((output / "manifest.json").read_text())
            for record in manifest["cases"]:
                self.assertTrue((output / record["trace_file"]).is_file())
                self.assertEqual(json.loads((output / record["record_file"]).read_text()), record)
            self.assertEqual(json.loads((output / "status.json").read_text())["state"], "completed")
            with (output / "summary.csv").open(encoding="utf8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 4)
            for name, digest in json.loads((output / "checksums.json").read_text()).items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            with self.assertRaises(FileExistsError):
                execute_grid(output)

    def test_failure_is_missing_not_zero_or_unsettled(self):
        class Bad:
            def reset(self):
                pass
            def command(self, *args):
                raise TypeError("injected")
        def fail(plant, controller, scenario):
            return simulate(plant, Bad(), scenario)
        with patch("controlstresslab.stress_grid.simulate", side_effect=fail):
            records = [r for r, _ in cases(StressPlan((0, 0.15), (0,)))]
        self.assertTrue(all(r["classification"] == "execution_or_metric_failure" for r in records))
        self.assertTrue(all(r["incremental_load_iae_rad"] is None for r in records))
        self.assertTrue(all(r["pre_event_settled"] is None for r in records))
        self.assertEqual(summarize(records)[0]["pre_event_unknown"], 2)

    def test_interrupted_scan_keeps_checkpoint_and_exit_code(self):
        first = next(cases(StressPlan((0,), (0,))))
        def stop(plan):
            yield first
            raise SystemExit(3)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.stress_grid.cases", side_effect=stop):
            output = Path(temporary) / "stopped"
            with self.assertRaises(SystemExit) as raised:
                execute_grid(output, StressPlan((0,), (0,)))
            self.assertEqual(raised.exception.code, 3)
            status = json.loads((output / "status.json").read_text())
            self.assertEqual(status["state"], "interrupted")
            self.assertEqual(status["written_runs"], 1)
            self.assertFalse(status["artifacts_complete"])
            self.assertTrue((output / first[0]["trace_file"]).is_file())

    def test_archive_preserves_report_and_matching_sources(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary:
            source, destination = Path(temporary) / "grid", Path(temporary) / "archive"
            execute_grid(source, StressPlan((0,), (0,)))
            (source / "README.md").write_text("original guide", encoding="utf8")
            checksums = json.loads((source / "checksums.json").read_text())
            checksums["README.md"] = hashlib.sha256((source / "README.md").read_bytes()).hexdigest()
            (source / "checksums.json").write_text(json.dumps(checksums), encoding="utf8")
            zipped = archive(source, destination)
            self.assertEqual((source / "report.html").read_bytes(), (destination / "report.html").read_bytes())
            with zipfile.ZipFile(zipped) as stream:
                self.assertIsNone(stream.testzip())
                self.assertEqual(stream.read("archive/report.html"), (source / "report.html").read_bytes())
            self.assertTrue((destination / "source/stress_grid.py").is_file())
            self.assertEqual((destination / "README.md").read_text(), "original guide")
            self.assertTrue((destination / "ARCHIVE_README.md").is_file())
            with self.assertRaises(FileExistsError):
                archive(source, destination)

    def test_archive_rejects_modified_experiment_before_copying(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary:
            source, destination = Path(temporary) / "grid", Path(temporary) / "archive"
            execute_grid(source, StressPlan((0,), (0,)))
            (source / "report.html").write_text("changed", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "checksum"):
                archive(source, destination)
            self.assertFalse(destination.exists())
