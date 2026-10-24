"""Desktop/CLI evidence contracts, independent of Qt and optional charts."""
from copy import deepcopy
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
from controlstresslab.experiment import (Cancelled, MODELS, default_config, execute,
    export_zip, load_result, presets, read_trace, scenario_for, validate_config)
from controlstresslab.benchmark_design import controller_for, DEFAULT_CONFIG
from controlstresslab.benchmark import execute as benchmark
from controlstresslab.coverage import COLUMN_MAP
from controlstresslab.simulation import simulate


class ExperimentChecks(unittest.TestCase):
    def test_presets_valid_detached_and_honest_recovery(self):
        for c in presets(): self.assertEqual(validate_config(c), c)
        self.assertEqual(scenario_for(presets()[1]).recovery_mode, "tracking_only")
        c = default_config()
        self.assertEqual(scenario_for(c).recovery_mode, "settling")
        d = validate_config(c); d["plant"]["gain"] = 9
        self.assertEqual(c["plant"]["gain"], 1)
        c["disturbance"].update(kind="sine")
        self.assertEqual(scenario_for(c).recovery_mode, "tracking_only")

    def test_strict_validation_no_directory_created(self):
        changes = [("extra", 1), ("model", []), ("selected_controllers", []),
                   ("selected_controllers", ["PI", "PI"]), ("name", ""), ("schema", "future")]
        for key, value in changes:
            c = default_config(); c[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_config(c)
        for group, key, value in [("plant", "gain", True), ("plant", "tau_s", 0),
            ("reference", "seed", 1.5), ("reference", "amplitude", float("nan")),
            ("conditions", "dt_s", True), ("conditions", "seed", True),
            ("conditions", "measurement_delay_s", .015), ("conditions", "reference_scale", 0)]:
            c = default_config(); c[group][key] = value
            with self.subTest(group=group, key=key), self.assertRaises(ValueError): validate_config(c)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"invalid"; c = default_config(); c["plant"]["tau_s"] = -1
            with self.assertRaises(ValueError): execute(p, c)
            self.assertFalse(p.exists())

    def test_controller_names_cannot_hide_other_semantics(self):
        for index, key, value in [(0, "kd", 1), (0, "anti_windup", True), (1, "anti_windup", False)]:
            c = default_config(); c["controllers"][index]["parameters"][key] = value
            with self.assertRaises(ValueError): validate_config(c)
        c = default_config(); c["selected_controllers"] = ["LADRC"]
        c["controllers"][-1]["parameters"]["observer_bandwidth"] = 21
        with self.assertRaises(ValueError): validate_config(c)

    def test_full_traces_match_direct_core_for_all_algorithms_and_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            for model in MODELS:
                c = default_config(model); c["selected_controllers"] = [x["name"] for x in c["controllers"]]
                c["conditions"].update(noise_std=.01, measurement_delay_s=.07)
                c["plant"]["initial_output"] = .12
                path = Path(tmp)/model
                execute(path, c)
                loaded = load_result(path)
                self.assertEqual(loaded["verification"], "校验通过")
                self.assertTrue(loaded["status"]["artifacts_complete"])
                self.assertEqual(len(loaded["records"]), 4)
                hashes = {r["input_sha256"] for r in loaded["records"]}
                self.assertEqual(len(hashes), 1)
                s = scenario_for(c)
                for record in loaded["records"]:
                    params = next(d["parameters"] for d in c["controllers"] if d["name"] == record["controller_name"])
                    direct = simulate(MODELS[model](**c["plant"]), controller_for(record["controller_name"], params), s)
                    rows = read_trace(path, record)
                    self.assertEqual(len(rows), len(direct.rows))
                    for actual, expected in zip(rows, direct.rows):
                        for generic, old in COLUMN_MAP.items():
                            if generic not in ("action_taken", "transition_completed"):
                                self.assertEqual(actual[generic], expected[old])
                    self.assertIsNone(rows[-1]["applied_input"])
                    self.assertIn("noise", json.loads((path/"inputs.json").read_text(encoding="utf8")))

    def test_configuration_changes_cause_different_trajectories(self):
        c = default_config()
        s = scenario_for(c)
        p = c["controllers"][1]["parameters"]
        baseline = simulate(MODELS["first_order"](), controller_for("PID_aw", p), s)
        c["plant"]["tau_s"] = 2
        c["reference"]["amplitude"] = .7
        changed = simulate(MODELS["first_order"](**c["plant"]), controller_for("PID_aw", p), scenario_for(c))
        self.assertNotEqual(baseline.rows[150]["true_output_rad_s"], changed.rows[150]["true_output_rad_s"])

    def test_no_overwrite_zip_roundtrip_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"run"; execute(p, default_config())
            with self.assertRaises(FileExistsError): execute(p, default_config())
            archive = export_zip(p, Path(tmp)/"report.zip")
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(z.read("run/config.json"), (p/"config.json").read_bytes())
            with self.assertRaises(FileExistsError): export_zip(p, archive)
            with self.assertRaises(ValueError): export_zip(p, p/"inside.zip")
            trace = p/"runs/PID_aw.csv"; trace.write_bytes(trace.read_bytes()+b"changed")
            self.assertEqual(load_result(p)["verification"], "校验不一致")
            with self.assertRaises(ValueError): export_zip(p, Path(tmp)/"bad.zip")

    def test_cancel_retains_completed_records_and_cannot_export_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"cancelled"
            with self.assertRaises(Cancelled):
                execute(p, default_config(), should_cancel=lambda: (p/"runs/PI.json").exists())
            result = load_result(p)
            self.assertEqual(result["status"]["state"], "interrupted")
            self.assertFalse(result["status"]["artifacts_complete"])
            self.assertEqual(len(result["records"]), 1)
            self.assertEqual(result["records"][0]["controller_name"], "PI")
            with self.assertRaises(ValueError): export_zip(p, Path(tmp)/"bad.zip")

    def test_failed_simulation_metrics_stay_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = default_config(); c["conditions"]["output_bound"] = .001
            p = Path(tmp)/"failed"; _, failed = execute(p, c)
            result = load_result(p)
            self.assertEqual(failed, 2)
            self.assertEqual(result["status"]["state"], "completed_with_failures")
            for r in result["records"]:
                self.assertIsNone(r["metrics"]["rmse"])
                self.assertTrue(r["metrics"]["reason"])

    def test_plot_failure_preserves_raw_and_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"plot_failure"
            with patch("controlstresslab.experiment_plots.build", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError): execute(p, default_config(), plots=True)
            result = load_result(p)
            self.assertEqual(result["status"]["state"], "export_failure")
            self.assertFalse(result["manifest"]["artifacts_complete"])
            self.assertEqual(len(result["records"]), 2)

    def test_path_escape_empty_checksums_and_unlisted_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"run"; execute(p, default_config())
            record = load_result(p)["records"][0]
            record["trace_file"] = "../outside.csv"
            with self.assertRaises(ValueError): read_trace(p, record)
            (p/"unexpected.txt").write_text("unlisted")
            self.assertEqual(load_result(p)["verification"], "校验不一致")
            archive = {name: hashlib.sha256((p/name).read_bytes()).hexdigest() for name in ("checksums.json", "unexpected.txt")}
            (p/"archive_manifest.json").write_text(json.dumps(dict(files_sha256=archive)))
            self.assertEqual(load_result(p)["verification"], "校验通过")
            (p/"unexpected.txt").write_text("changed snapshot")
            self.assertEqual(load_result(p)["verification"], "校验不一致")
            (p/"checksums.json").write_text("{}")
            with self.assertRaises(ValueError): load_result(p)

    def test_cancelled_export_never_creates_complete_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"run"; execute(p, default_config())
            dest = Path(tmp)/"cancelled.zip"; calls = []
            def cancel(): calls.append(1); return len(calls) > 3
            with self.assertRaises(Cancelled): export_zip(p, dest, should_cancel=cancel)
            self.assertFalse(dest.exists())
            self.assertTrue(list(Path(tmp).glob("*.partial-*")))
            self.assertEqual(load_result(p)["verification"], "校验通过")

    def test_benchmark_cancel_stops_before_heldout(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = deepcopy(DEFAULT_CONFIG)
            c.update(models=["first_order"], controllers=["PI"], candidate_budget=2, heldout_seeds=[101], parameter_factors=[1])
            p = Path(tmp)/"benchmark"; events = []
            with self.assertRaises(Cancelled):
                benchmark(p, c, progress=events.append, should_cancel=lambda: True)
            self.assertEqual(load_result(p)["status"]["state"], "interrupted")
            self.assertFalse((p/"selections.json").exists())
            self.assertFalse(any(e.get("stage") == "heldout_started" for e in events))


if __name__ == "__main__": unittest.main()
