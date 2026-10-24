"""Check comparison failure detection, timing contracts and reference isolation."""

import ast
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from reference_checks import compare_case, compare_channel, product, reference_metrics, suite


class ReferenceComparisonChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = suite()

    def test_predeclared_suite(self):
        cases = self.inputs["cases"]
        self.assertEqual(len(cases), 54)
        self.assertEqual(len({c["id"] for c in cases}), 54)
        self.assertEqual([sum(c["path"] == p for c in cases) for p in ("open_loop", "linear_pi", "ode_closed_loop")], [18, 6, 30])

    def test_nan_length_and_shift_cannot_pass(self):
        for a, b in (([1], []), ([], []), ([float("nan")], [1]), ([1, 2], [2, 1]), ([True], [1])):
            with self.subTest(a=a, b=b):
                self.assertFalse(compare_channel(a, b)["passed"])

    def test_samplewise_rule_not_only_max_relative_error(self):
        self.assertTrue(compare_channel([1000 + 1e-7, 0], [1000, 0])["passed"])
        self.assertFalse(compare_channel([1000, 1e-7], [1000, 0])["passed"])

    def test_times_are_exact_and_nulls_not_zero(self):
        self.assertFalse(compare_channel([0.01+1e-15], [0.01], exact=True)["passed"])
        self.assertFalse(compare_channel([None], [0])["passed"])

    def test_product_terminal_no_fictitious_action(self):
        for c in self.inputs["cases"]:
            p = product(c)
            self.assertEqual(len(p["channels"]["output"]), c["intervals"] + 1)
            self.assertIsNone(p["channels"]["command"][-1])

    def test_integrator_sign_and_timing_mutation_is_detected(self):
        c = next(c for c in self.inputs["cases"] if c["path"] == "linear_pi")
        p = product(c)
        ref = copy.deepcopy(p["channels"])
        self.assertTrue(compare_case(c, p, ref)["passed"])
        ref["command"][50] += 0.01
        self.assertFalse(compare_case(c, p, ref)["passed"])

    def test_missing_state_and_fictitious_terminal_rejected(self):
        c = next(c for c in self.inputs["cases"] if c["path"] == "linear_pi")
        p = product(c)
        ref = copy.deepcopy(p["channels"])
        ref["command"][-1] = 0
        self.assertFalse(compare_case(c, p, ref)["passed"])
        ref = copy.deepcopy(p["channels"])
        ref["output"][0] = p["channels"]["output"][0] = None
        self.assertFalse(compare_case(c, p, ref)["passed"])

    def test_metric_uses_left_samples_excludes_terminal(self):
        c = copy.deepcopy(self.inputs["cases"][0])
        c.update(intervals=2, dt_s=0.5, reference=((0, 0),))
        c["scenario"].update(evaluation_start_s=0, recovery_start_s=0, recovery_band=1, recovery_dwell_s=0.5)
        m = reference_metrics(c, {"output": [2, 0, 100]})
        self.assertEqual(m["iae_rad"], 1)
        self.assertEqual(m["recovery_status"], "not_recovered_in_observation_window")

    def test_recovery_uses_final_continuous_tail(self):
        c = copy.deepcopy(self.inputs["cases"][0])
        c.update(intervals=4, dt_s=0.5, reference=((0, 0),))
        c["scenario"].update(evaluation_start_s=0, recovery_start_s=0, recovery_band=1, recovery_dwell_s=0.5)
        m = reference_metrics(c, {"output": [2, 0, 2, 0, 0]})
        self.assertEqual(m["recovery_time_s"], 1.5)

    def test_oracle_has_no_product_import_or_product_input(self):
        text = (ROOT / "scripts/scipy_reference.py").read_text(encoding="utf8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("controlstresslab", node.module or "")
            elif isinstance(node, ast.Import):
                self.assertFalse(any("controlstresslab" in n.name for n in node.names))
        self.assertNotIn("product.json", text)


if __name__ == "__main__":
    unittest.main()
