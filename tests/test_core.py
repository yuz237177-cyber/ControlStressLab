"""Independent formula, timing, fairness, failure and end-to-end checks."""

from dataclasses import replace
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_TEMP = ROOT / "outputs"

from controlstresslab import DCMotor, FirstOrder, PID, Scenario, StepSignal, simulate
from controlstresslab.cli import execute_demo
from controlstresslab.metrics import evaluate


class ConstantController:
    def __init__(self, value):
        self.value = value

    def reset(self):
        pass

    def command(self, reference, measurement, dt):
        return self.value

    def observe_applied(self, applied):
        pass


class AnalyticalChecks(unittest.TestCase):
    def test_first_order_step_matches_closed_form(self):
        plant = FirstOrder(gain=2.0, tau_s=0.7, initial_output=1.0)
        for _ in range(100):
            plant.advance(3.0, 0.0, 0.01)
        expected = 6.0 + (1.0 - 6.0) * math.exp(-1.0 / 0.7)
        self.assertAlmostEqual(plant.output, expected, places=12)

    def test_motor_matches_independent_step_response(self):
        motor = DCMotor()
        motor.advance(6.0, 0.15, 2.0)
        # Default equation independently reduces to domega/dt = 45 - 1.1*omega.
        expected = 45.0 / 1.1 * (1.0 - math.exp(-2.2))
        self.assertAlmostEqual(motor.output, expected, places=12)

    def test_motor_split_hold_has_same_endpoint(self):
        a, b = DCMotor(initial_output=12.0), DCMotor(initial_output=12.0)
        a.advance(5.0, 0.1, 1.0)
        for _ in range(1000):
            b.advance(5.0, 0.1, 0.001)
        self.assertAlmostEqual(a.output, b.output, places=10)

    def test_load_sign_and_nonzero_initial_state(self):
        a, b = DCMotor(initial_output=20.0), DCMotor(initial_output=20.0)
        a.advance(5.0, 0.0, 0.2)
        b.advance(5.0, 0.2, 0.2)
        self.assertLess(b.output, a.output)
        b.reset()
        self.assertEqual(b.output, 20.0)


class TimingAndFairnessChecks(unittest.TestCase):
    def test_delay_is_on_measurement_not_plant(self):
        scenario = Scenario(dt_s=0.1, duration_s=2.0, measurement_delay_s=0.2)
        run = simulate(FirstOrder(), ConstantController(1.0), scenario)
        for k, row in enumerate(run.rows):
            expected = run.rows[k - 2]["true_output_rad_s"] if k >= 2 else 0.0
            self.assertAlmostEqual(row["measurement_rad_s"], expected)
        self.assertGreater(run.rows[1]["true_output_rad_s"], 0.0)
        self.assertEqual(run.rows[1]["measurement_rad_s"], 0.0)

    def test_noise_is_delayed_together_with_measurement(self):
        scenario = Scenario(dt_s=0.1, duration_s=2.0, measurement_delay_s=0.2, noise_std=0.7)
        run = simulate(FirstOrder(), ConstantController(0.0), scenario)
        noise = scenario.noise_sequence()
        self.assertEqual(run.rows[0]["measurement_rad_s"], 0.0)
        self.assertAlmostEqual(run.rows[2]["measurement_rad_s"], noise[0])

    def test_noise_is_paired_even_with_different_control_actions(self):
        scenario = Scenario(noise_std=1.0)
        a = simulate(DCMotor(), ConstantController(1.0), scenario)
        b = simulate(DCMotor(), ConstantController(2.0), scenario)
        for ra, rb in zip(a.rows, b.rows):
            na = ra["measurement_rad_s"] - ra["true_output_rad_s"]
            nb = rb["measurement_rad_s"] - rb["true_output_rad_s"]
            self.assertAlmostEqual(na, nb, places=12)

    def test_repeated_runs_reset_all_state(self):
        plant, controller, scenario = DCMotor(), PID(kd=0.01), Scenario(noise_std=1.0)
        a = simulate(plant, controller, scenario)
        b = simulate(plant, controller, scenario)
        self.assertEqual(a.rows, b.rows)

    def test_limit_is_applied_before_plant_update(self):
        scenario = Scenario(dt_s=0.1, duration_s=2.0, voltage_limit=2.0)
        run = simulate(FirstOrder(), ConstantController(100.0), scenario)
        self.assertEqual(run.rows[0]["command_V"], 100.0)
        self.assertEqual(run.rows[0]["applied_V"], 2.0)
        self.assertAlmostEqual(run.rows[1]["true_output_rad_s"], 2.0 * (1 - math.exp(-0.1)))

    def test_step_is_right_continuous_and_no_extra_endpoint_action(self):
        scenario = Scenario(dt_s=0.1, duration_s=2.0)
        run = simulate(FirstOrder(), ConstantController(1.0), scenario)
        self.assertEqual(run.rows[4]["reference_rad_s"], 0.0)
        self.assertEqual(run.rows[5]["reference_rad_s"], 60.0)
        self.assertEqual(len(run.rows), 21)
        self.assertEqual(run.rows[-1]["interval_s"], 0.0)
        self.assertAlmostEqual(run.rows[-1]["true_output_rad_s"], 1 - math.exp(-2.0))

    def test_antiwindup_releases_saturation(self):
        plain, protected = PID(kp=0.0, ki=1.0), PID(kp=0.0, ki=1.0, anti_windup=True)
        for _ in range(100):
            for controller in (plain, protected):
                requested = controller.command(100.0, 0.0, 0.1)
                controller.observe_applied(max(-1.0, min(1.0, requested)))
        self.assertGreater(plain.command(0.0, 0.0, 0.1), 100.0)
        self.assertEqual(protected.command(0.0, 0.0, 0.1), 0.0)

    def test_no_derivative_kick_from_reference_step(self):
        controller = PID(kp=0.0, ki=0.0, kd=1.0)
        self.assertEqual(controller.command(0.0, 0.0, 0.1), 0.0)
        controller.observe_applied(0.0)
        self.assertEqual(controller.command(100.0, 0.0, 0.1), 0.0)


class MetricAndFailureChecks(unittest.TestCase):
    def test_constant_error_metrics_use_real_duration(self):
        s = Scenario(dt_s=0.1, duration_s=2.0, evaluation_start_s=0.0, recovery_start_s=0.0,
                     reference=StepSignal(((0.0, 2.0),)))
        metrics = evaluate(simulate(FirstOrder(), ConstantController(0.0), s))
        self.assertAlmostEqual(metrics["rmse_rad_s"], 2.0)
        self.assertAlmostEqual(metrics["iae_rad"], 4.0)
        self.assertIsNone(metrics["recovery_time_s"])
        self.assertEqual(metrics["recovery_status"], "not_recovered_in_observation_window")

    def test_recovery_requires_final_uninterrupted_dwell(self):
        s = Scenario(dt_s=0.1, duration_s=2.0, evaluation_start_s=0.0, recovery_start_s=0.0,
                     recovery_band=0.1, reference=StepSignal(((0.0, 0.0),)))
        run = simulate(FirstOrder(), ConstantController(0.0), s)
        # Enter band early, then leave at 1.8 s: there is insufficient final dwell.
        run.rows[-3]["true_output_rad_s"] = 1.0
        self.assertIsNone(evaluate(run)["recovery_time_s"])

    def test_metrics_use_true_output_not_measurement(self):
        s = Scenario(noise_std=50.0, reference=StepSignal(((0.0, 0.0),)))
        metrics = evaluate(simulate(DCMotor(), ConstantController(0.0), s))
        self.assertEqual(metrics["rmse_rad_s"], 0.0)

    def test_bound_failure_does_not_win_via_shorter_integration(self):
        s = Scenario(output_bound=0.1)
        run = simulate(DCMotor(), ConstantController(12.0), s)
        self.assertEqual(run.status, "bound_exceeded")
        self.assertIsNone(evaluate(run)["iae_rad"])

    def test_nonfinite_controller_is_explicit_failure(self):
        run = simulate(DCMotor(), ConstantController(float("nan")), Scenario())
        self.assertEqual(run.status, "numerical_failure")
        self.assertIsNone(evaluate(run)["rmse_rad_s"])

    def test_initial_output_bound_is_checked(self):
        run = simulate(DCMotor(initial_output=20.0), PID(), Scenario(output_bound=10.0))
        self.assertEqual(run.status, "bound_exceeded")


class ConfigurationChecks(unittest.TestCase):
    def test_rejects_fractional_delay_samples(self):
        with self.assertRaises(ValueError):
            Scenario(measurement_delay_s=0.015)

    def test_rejects_unaligned_step(self):
        with self.assertRaises(ValueError):
            Scenario(load=StepSignal(((0.0, 0.0), (0.123, 1.0))))

    def test_rejects_reference_change_after_recovery_start(self):
        with self.assertRaises(ValueError):
            Scenario(reference=StepSignal(((0.0, 0.0), (1.0, 10.0))))

    def test_rejects_invalid_parameters_and_false_evidence(self):
        for kwargs in ({"dt_s": 0}, {"noise_std": -1}, {"output_bound": float("inf")},
                       {"evidence": "hardware_validated"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Scenario(**kwargs)
        with self.assertRaises(ValueError):
            DCMotor(inertia_kg_m2=-1)


class EndToEndChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep generated test directories inside this checkout, including sandboxed Windows.
        TEST_TEMP.mkdir(exist_ok=True)

    def test_report_manifest_hashes_and_repeated_seed_outputs(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temporary:
            a, b = Path(temporary) / "a", Path(temporary) / "b"
            execute_demo(a, seeds=(17,))
            execute_demo(b, seeds=(17,))
            manifest = json.loads((a / "manifest.json").read_text(encoding="utf8"))
            self.assertEqual(len(manifest["runs"]), 10)
            self.assertFalse(manifest["hardware_validated"])
            self.assertTrue(all(r["metrics"]["status"] == "completed" for r in manifest["runs"]))
            for filename, digest in json.loads((a / "checksums.json").read_text()).items():
                self.assertEqual(hashlib.sha256((a / filename).read_bytes()).hexdigest(), digest)
            for filename in a.glob("*.csv"):
                self.assertEqual(filename.read_bytes(), (b / filename.name).read_bytes())
            self.assertIn("NOT HARDWARE VALIDATED", (a / "report.html").read_text(encoding="utf8"))
            with self.assertRaises(FileExistsError):
                execute_demo(a)

    def test_cli_from_clean_source_checkout(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temporary:
            output = Path(temporary) / "cli"
            result = subprocess.run([sys.executable, str(ROOT / "run_demo.py"), "--output", str(output)],
                                    capture_output=True, text=True, encoding="utf8", errors="replace", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "report.html").is_file())
            with (output / "summary.csv").open(encoding="utf8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 10)

    def test_invalid_cli_configuration_leaves_no_output(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temporary:
            output = Path(temporary) / "invalid"
            result = subprocess.run([sys.executable, str(ROOT / "run_demo.py"), "--dt", "0.03", "--output", str(output)],
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
