"""Search leakage, paired conditions, constraint selection and transactional exports."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from controlstresslab.benchmark_design import (DEFAULT_CONFIG, FAMILIES, TRAINING, assess_candidate,
    candidate_parameters, controller_for, heldout_cases, plant_for, scenario_for, select_candidate, validate_config)
from controlstresslab.benchmark import SelectionError, execute, summarize


def small_config():
    c = deepcopy(DEFAULT_CONFIG)
    c.update(models=["first_order"], controllers=["PI"], candidate_budget=2, heldout_seeds=[101], parameter_factors=[1])
    return c


class DesignChecks(unittest.TestCase):
    def test_default_file_matches_protocol_and_counts(self):
        config = json.loads((ROOT / "configs/benchmark-v0.3.json").read_text())
        self.assertEqual(validate_config(config), DEFAULT_CONFIG)
        self.assertEqual(len(heldout_cases(config)), 24)
        self.assertEqual(2*4*32*3+2*4*2*24, 1152)

    def test_strict_unknown_missing_and_types(self):
        for key, value in (("extra", 1), ("models", ["motor"]), ("models", [["first_order"]]),
            ("controllers", ["PI", "PI"]), ("candidate_budget", True), ("candidate_budget", 129),
            ("search_seed", -1), ("heldout_seeds", [True]), ("heldout_seeds", [1, 1]),
            ("parameter_factors", [float("nan")]), ("parameter_factors", [0]),
            ("parameter_factors", [1, 1.0]), ("max_training_variation_rate", float("inf")),
            ("max_training_saturation_fraction", 1.1), ("protocol", "unknown")):
            c = deepcopy(DEFAULT_CONFIG)
            c[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): validate_config(c)
        c = deepcopy(DEFAULT_CONFIG)
        del c["search_seed"]
        with self.assertRaises(ValueError): validate_config(c)

    def test_validation_detaches_mutable_config(self):
        c = validate_config(DEFAULT_CONFIG)
        c["models"].clear()
        self.assertEqual(len(DEFAULT_CONFIG["models"]), 2)

    def test_candidates_are_deterministic_budgeted_and_paired(self):
        c = DEFAULT_CONFIG
        a = candidate_parameters("second_order", "PID_aw", c)
        self.assertEqual(len(a), 32)
        self.assertEqual(a, candidate_parameters("second_order", "PID_aw", c))
        pi, two = [candidate_parameters("second_order", n, c) for n in ("PI", "TwoDOF_PID")]
        for i in range(32):
            for key in ("kp", "ki"):
                self.assertEqual(a[i][key], pi[i][key])
                self.assertEqual(a[i][key], two[i][key])

    def test_candidate_bounds_and_nominal_knowledge(self):
        for model in DEFAULT_CONFIG["models"]:
            for name in DEFAULT_CONFIG["controllers"]:
                for params in candidate_parameters(model, name, DEFAULT_CONFIG):
                    controller_for(name, params)
                    if name == "LADRC":
                        self.assertEqual(params["b0"], 1)
                        self.assertLessEqual(params["observer_bandwidth"]*0.01, 0.2)
        self.assertEqual(plant_for("first_order", 1.5).tau_s, 1.5)
        self.assertEqual(plant_for("second_order", 0.65).mass_kg, 0.65)

    def test_changing_heldout_does_not_change_candidates(self):
        c = deepcopy(DEFAULT_CONFIG)
        c.update(heldout_seeds=[999], parameter_factors=[2])
        self.assertEqual(candidate_parameters("first_order", "PID_aw", c), candidate_parameters("first_order", "PID_aw", DEFAULT_CONFIG))

    def test_predeclared_windows_and_tracking_modes(self):
        for model in DEFAULT_CONFIG["models"]:
            for f in TRAINING:
                s = scenario_for(model, f)
                self.assertEqual(s.evaluation_start_s, 6 if f == "disturbance_step" else 0.5)
                self.assertEqual(s.recovery_mode, "settling")
            for case in heldout_cases(DEFAULT_CONFIG):
                s = scenario_for(model, case["family"], case["seed"], heldout=True)
                self.assertEqual(s.duration_s, 12)
                self.assertEqual(s.recovery_mode, "settling" if case["family"] == "noise_delay" else "tracking_only")
                if case["family"] == "noise_delay": self.assertEqual(s.measurement_delay_s, 0.07)

    def test_paired_noise_is_reproducible_and_seeds_differ(self):
        a = scenario_for("first_order", "noise_delay", 101, heldout=True)
        b = scenario_for("first_order", "noise_delay", 202, heldout=True)
        self.assertEqual(a.noise_sequence(), a.noise_sequence())
        self.assertNotEqual(a.noise_sequence(), b.noise_sequence())


class SelectionChecks(unittest.TestCase):
    def metric(self, error=0.1, rate=0.2, saturation=0):
        return dict(status="completed", normalized_iae=error, input_variation_rate=rate, saturation_fraction=saturation)

    def candidate(self, index, **kw):
        return dict(candidate_index=index, assessment=assess_candidate([self.metric(**kw)]*3, DEFAULT_CONFIG))

    def test_reject_low_error_if_action_constraint_violated(self):
        best_error = self.candidate(0, error=0.01, rate=0.61)
        feasible = self.candidate(1, error=0.1)
        self.assertIs(select_candidate([best_error, feasible]), feasible)

    def test_saturation_and_exact_boundaries(self):
        self.assertFalse(self.candidate(0, saturation=0.251)["assessment"]["feasible"])
        self.assertTrue(self.candidate(0, rate=0.6, saturation=0.25)["assessment"]["feasible"])

    def test_failure_nonfinite_and_missing_not_zero_score(self):
        for m in (dict(self.metric(), status="failed"), dict(self.metric(), normalized_iae=None), dict(self.metric(), input_variation_rate=float("nan"))):
            a = assess_candidate([m]*3, DEFAULT_CONFIG)
            self.assertFalse(a["feasible"])
            self.assertIsNone(a["objective"])
        self.assertIsNone(select_candidate([self.candidate(0, rate=1)]))

    def test_tie_break_uses_index_not_input_order(self):
        a, b = self.candidate(3), self.candidate(1)
        self.assertIs(select_candidate([a, b]), b)

    def test_family_equal_weights_and_failure_invalidates_summary(self):
        def rec(f, v):
            return dict(model_name="first_order", controller_name="PI", phase="tuned", family=f,
                        metrics=dict(status="completed", normalized_iae=v, normalized_rmse=v, input_variation_rate=v, saturation_fraction=0))
        rows = [rec(f, i+1) for i, f in enumerate(FAMILIES)] + [rec("noise_delay", 4)]*2
        self.assertEqual(summarize(rows)[0]["normalized_iae"], 2.5)
        rows[0]["metrics"]["status"] = "failed"
        self.assertIsNone(summarize(rows)[0]["normalized_iae"])
        self.assertFalse(summarize(rows)[0]["comparable"])


class ExportChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "outputs").mkdir(exist_ok=True)

    def test_freeze_before_test_pairing_and_exact_hashes(self):
        from controlstresslab.benchmark import simulate as real_simulate
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "experiment"
            def guarded(plant, controller, scenario):
                if scenario.name.startswith("heldout_"):
                    self.assertTrue((out / "selections.json").exists())
                    events = [json.loads(line)["event"] for line in (out / "events.jsonl").read_text().splitlines()]
                    self.assertLess(events.index("selection_frozen"), events.index("heldout_started"))
                return real_simulate(plant, controller, scenario)
            with patch("controlstresslab.benchmark.simulate", side_effect=guarded):
                report, failed = execute(out, small_config())
            self.assertTrue(report.is_file())
            self.assertEqual(failed, 0)
            status = json.loads((out / "status.json").read_text())
            self.assertEqual((status["expected_runs"], status["written_runs"]), (14, 14))
            self.assertTrue(status["artifacts_complete"])
            checks = json.loads((out / "checksums.json").read_text())
            self.assertTrue(all(hashlib.sha256((out/n).read_bytes()).hexdigest() == h for n, h in checks.items()))
            records = [json.loads(p.read_text()) for p in (out / "runs").glob("heldout_*.json")]
            for family in FAMILIES:
                pair = [r for r in records if r["family"] == family]
                self.assertEqual(len({r["input_sha256"] for r in pair}), 1)
            with self.assertRaises(FileExistsError): execute(out, small_config())

    def test_no_feasible_candidate_stops_before_heldout(self):
        c = small_config()
        c.update(candidate_budget=1, max_training_variation_rate=0)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "experiment"
            with self.assertRaises(SelectionError): execute(out, c)
            self.assertFalse((out / "selections.json").exists())
            self.assertFalse(json.loads((out / "status.json").read_text())["artifacts_complete"])
            self.assertFalse(json.loads((out / "selection_failure.json").read_text())["heldout_started"])

    def test_validation_precedes_output_creation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "experiment"
            with self.assertRaises(ValueError): execute(out, dict(extra=True))
            self.assertFalse(out.exists())

    def test_checksum_write_failure_never_leaves_complete_state(self):
        from controlstresslab.benchmark import write_json as real_write
        def injected(path, data):
            if path.name == "checksums.json": raise OSError("injected export failure")
            return real_write(path, data)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "experiment"
            with patch("controlstresslab.benchmark.write_json", side_effect=injected), self.assertRaises(OSError):
                execute(out, small_config())
            self.assertFalse(json.loads((out / "status.json").read_text())["artifacts_complete"])
            self.assertFalse(json.loads((out / "manifest.json").read_text())["artifacts_complete"])

    def test_interrupt_propagates_and_retains_partial_status(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "experiment"
            with patch("controlstresslab.benchmark.simulate", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                execute(out, small_config())
            status = json.loads((out / "status.json").read_text())
            self.assertEqual(status["state"], "interrupted")
            self.assertFalse(status["artifacts_complete"])

    def test_independent_evidence_audit_checks_saved_artifacts(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from check_benchmark_evidence import audit
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "experiment"
            execute(out, small_config())
            result = audit(out)
            self.assertTrue(result["passed"])
            self.assertEqual(result["heldout_runs"], 8)
            target = out / "selections.json"
            target.write_text("{}", encoding="utf8")
            with self.assertRaises(AssertionError): audit(out)


if __name__ == "__main__": unittest.main()
