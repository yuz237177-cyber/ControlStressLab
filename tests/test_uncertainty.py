"""Contracts for parameter grids, fixed gains, baselines and incomplete outcomes."""

import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from controlstresslab import DCMotor, PID, simulate
from controlstresslab.cli import demo_scenarios
from controlstresslab.metrics import evaluate
from controlstresslab.uncertainty import SweepPlan, cases, execute_sweep, summarize


class PlanChecks(unittest.TestCase):
    def test_invalid_domains_rejected(self):
        for levels in ((), (0, 1), (True, 1), (1, float("inf")), (1, float("nan")), (1, 1), (2, 1), (0.5, 2)):
            with self.subTest(levels=levels), self.assertRaises(ValueError):
                SweepPlan(inertia_factors=levels)

    def test_resource_and_derived_parameter_limits(self):
        with self.assertRaisesRegex(ValueError, "2000"):
            SweepPlan(tuple(range(1, 100)), tuple(range(1, 100)))
        with self.assertRaises(ValueError):
            SweepPlan(inertia_factors=(1e-322, 1))

    def test_default_design_size_and_nominal_anchor(self):
        plan = SweepPlan()
        self.assertEqual(plan.expected_runs, 196)
        self.assertIn(1, plan.inertia_factors)
        self.assertIn(1, plan.friction_factors)


class GridChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = [r for r, _ in cases(SweepPlan((1, 2), (1, 2)))]

    def test_every_point_has_fresh_paired_controllers_with_fixed_gains(self):
        self.assertEqual(len(self.records), 16)
        self.assertEqual(len({r["case_id"] for r in self.records}), 16)
        for record in self.records:
            self.assertEqual(tuple(record["controller"][k] for k in ("kp", "ki", "kd")), (0.25, 0.8, 0))
            self.assertEqual(record["metrics"]["status"], "completed")
            self.assertEqual(record["plant"]["initial_output"], 0)

    def test_nominal_anchor_reproduces_original_suite(self):
        scenarios = {s.name: s for s in demo_scenarios(0.01, 42)}
        for record in self.records:
            if record["inertia_factor"] == record["friction_factor"] == 1:
                expected = evaluate(simulate(DCMotor(), PID(anti_windup=record["controller_name"] == "pid_antiwindup"), scenarios[record["scenario"]]))
                self.assertEqual(record["metrics"], expected)

    def test_physical_parameter_mapping_and_damping_explanation(self):
        def point(j, b):
            return next(r for r in self.records if r["scenario"] == "nominal" and r["controller_name"] == "pid" and r["inertia_factor"] == j and r["friction_factor"] == b)
        base, inertia, friction = point(1, 1), point(2, 1), point(1, 2)
        self.assertAlmostEqual(inertia["plant"]["inertia_kg_m2"], 0.02)
        self.assertAlmostEqual(friction["plant"]["friction_Nm_s"], 0.002)
        self.assertAlmostEqual(inertia["derived"]["time_constant_s"], 2 * base["derived"]["time_constant_s"])
        self.assertEqual(inertia["derived"]["dc_gain_rad_s_per_V"], base["derived"]["dc_gain_rad_s_per_V"])
        self.assertAlmostEqual(friction["derived"]["damping_Nm_s"] / base["derived"]["damping_Nm_s"], 12 / 11)

    def test_normalization_uses_own_controller_and_scenario(self):
        records = json.loads(json.dumps(self.records))
        groups = summarize(records)
        self.assertEqual(len(groups), 4)
        for record in records:
            if record["inertia_factor"] == record["friction_factor"] == 1:
                self.assertEqual(record["post_iae_ratio_to_own_nominal"], 1)
        for group in groups:
            valid = [r["metrics"]["iae_post_event_rad"] for r in records if r["scenario"] == group["scenario"] and r["controller_name"] == group["controller_name"]]
            self.assertEqual(group["max_valid_sampled_post_iae_rad"], max(valid))

    def test_zero_baseline_and_failed_outcome_never_become_zero_ratio(self):
        records = json.loads(json.dumps(self.records))
        base = next(r for r in records if r["scenario"] == "nominal" and r["controller_name"] == "pid" and r["inertia_factor"] == r["friction_factor"] == 1)
        bad = next(r for r in records if r["scenario"] == "nominal" and r["controller_name"] == "pid" and r["inertia_factor"] == 2 and r["friction_factor"] == 1)
        base["metrics"]["iae_post_event_rad"] = 0
        bad["metrics"].update(status="numerical_failure", iae_post_event_rad=None)
        groups = summarize(records)
        self.assertIsNone(base["post_iae_ratio_to_own_nominal"])
        self.assertIsNone(bad["post_iae_ratio_to_own_nominal"])
        self.assertEqual(groups[0]["failed"], 1)

    def test_incremental_load_metric_matches_paired_output_integral(self):
        scenarios = {s.name: s for s in demo_scenarios(0.01, 42)}
        loaded = simulate(DCMotor(inertia_kg_m2=0.02), PID(), scenarios["load_step"])
        unloaded = simulate(DCMotor(inertia_kg_m2=0.02), PID(), scenarios["nominal"])
        self.assertEqual([r["true_output_rad_s"] for r in loaded.rows if r["time_s"] <= 4],
                         [r["true_output_rad_s"] for r in unloaded.rows if r["time_s"] <= 4])
        expected = sum(abs(a["true_output_rad_s"] - b["true_output_rad_s"]) * a["interval_s"] for a, b in zip(loaded.rows, unloaded.rows)
                       if a["time_s"] >= 4 and a["interval_s"] > 0)
        record = next(r for r in self.records if r["scenario"] == "load_step" and r["controller_name"] == "pid" and r["inertia_factor"] == 2 and r["friction_factor"] == 1)
        self.assertAlmostEqual(record["incremental_load_iae_rad"], expected, places=12)
        self.assertNotAlmostEqual(record["metrics"]["iae_post_event_rad"], expected, places=4)


class SweepExportChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "outputs").mkdir(exist_ok=True)

    def test_export_configuration_selected_traces_and_checksums(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary:
            target = Path(temporary) / "sweep"
            execute_sweep(target, SweepPlan((1, 2), (1, 2)))
            plan = json.loads((target / "plan.json").read_text())
            self.assertFalse(plan["controller_retuning"])
            self.assertIsNone(plan["probability_distribution"])
            data = json.loads((target / "manifest.json").read_text())
            self.assertEqual(len(data["cases"]), 16)
            for record in data["cases"]:
                self.assertEqual(json.loads((target / record["record_file"]).read_text()), record)
            for group in data["groups"]:
                for case in (group["nominal_case"], group["worst_valid_sampled_case"]):
                    record = next(r for r in data["cases"] if r["case_id"] == case)
                    self.assertTrue((target / record["trace_file"]).is_file())
            for name, digest in json.loads((target / "checksums.json").read_text()).items():
                self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), digest)
            with (target / "summary.csv").open(encoding="utf8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 16)
            self.assertTrue(json.loads((target / "status.json").read_text())["artifacts_complete"])
            with self.assertRaises(FileExistsError):
                execute_sweep(target)

    def test_failure_is_retained_separately_and_batch_continues(self):
        class BadController:
            def reset(self):
                pass
            def command(self, *args):
                raise TypeError("injected")
        def fail(plant, controller, scenario):
            return simulate(plant, BadController(), scenario)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.uncertainty.simulate", side_effect=fail):
            target = Path(temporary) / "failed"
            execute_sweep(target, SweepPlan((1,), (1,)))
            data = json.loads((target / "manifest.json").read_text())
            self.assertEqual(len(data["cases"]), 4)
            for group in data["groups"]:
                self.assertEqual(group["failed"], 1)
                self.assertIsNone(group["worst_valid_sampled_case"])
            self.assertTrue(all(r["post_iae_ratio_to_own_nominal"] is None for r in data["cases"]))
            self.assertTrue(all(r["incremental_load_effect_status"] == "paired_run_incomplete" for r in data["cases"] if r["scenario"] == "load_step"))
            self.assertEqual(json.loads((target / "status.json").read_text())["state"], "completed_with_failures")

    def test_interruption_keeps_completed_case_checkpoint(self):
        first = next(cases(SweepPlan((1,), (1,))))
        def interrupted(plan):
            yield first
            raise SystemExit(3)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.uncertainty.cases", side_effect=interrupted):
            target = Path(temporary) / "interrupted"
            with self.assertRaises(SystemExit) as raised:
                execute_sweep(target, SweepPlan((1,), (1,)))
            self.assertEqual(raised.exception.code, 3)
            status = json.loads((target / "status.json").read_text())
            self.assertEqual(status["state"], "interrupted")
            self.assertEqual(status["written_runs"], 1)
            self.assertFalse(status["artifacts_complete"])
            self.assertTrue((target / first[0]["record_file"]).is_file())
