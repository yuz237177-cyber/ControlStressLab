"""Signal contracts, physical solutions, observer information boundaries and exports."""

import csv
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
from controlstresslab import (FirstOrder, InductiveDCMotor, MassSpringDamper, LinearADRC,
                              PID, TwoDOFPID, SampledSignal, Scenario, simulate, waveform)
from controlstresslab.coverage import (MODEL_NAMES, SCENARIO_NAMES, controllers, execute,
                                      model_spec, neutral_metrics, scenario)
from controlstresslab.metrics import evaluate


class WaveformChecks(unittest.TestCase):
    def test_step_pulse_and_ramp_boundaries(self):
        step, pulse, ramp = [waveform(k) for k in ("step", "pulse", "ramp")]
        self.assertEqual((step.at(0.49), step.at(0.5)), (0, 1))
        self.assertEqual((pulse.at(1.49), pulse.at(1.5)), (1, 0))
        self.assertEqual((ramp.at(0.5), ramp.at(2.5), ramp.at(4.5), ramp.at(16)), (0, 0.5, 1, 1))
        self.assertEqual(step.at(0.505), 1)

    def test_periodic_quarter_cycles(self):
        for kind in ("sine", "triangle", "square"):
            with self.subTest(kind=kind):
                signal = waveform(kind)
                self.assertAlmostEqual(signal.at(1.5), 1)
                self.assertAlmostEqual(signal.at(3.5), -1)

    def test_binary_blocks_are_seeded_and_paired(self):
        a, b, c = waveform("prbs"), waveform("prbs"), waveform("prbs", seed=11)
        self.assertEqual(a, b)
        self.assertNotEqual(a.values, c.values)
        self.assertEqual(set(a.values), {-1, 0, 1})
        for i in range(50, 1600, 50):
            self.assertEqual(len(set(a.values[i:i+50])), 1)

    def test_signal_domain_and_resource_checks(self):
        for kwargs in (dict(kind="unknown"), dict(kind="step", start_s=0.015), dict(kind="sine", frequency_hz=11),
                       dict(kind="chirp", stop_frequency_hz=11), dict(kind="pulse", pulse_width_s=16),
                       dict(kind="step", amplitude=float("nan")), dict(kind="step", duration_s=3000)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): waveform(**kwargs)
        with self.assertRaises(ValueError): waveform("step").at(16.01)
        with self.assertRaises(ValueError): SampledSignal(0.01, (1, float("inf")))

    def test_sample_grid_cannot_silently_resample(self):
        with self.assertRaises(ValueError): Scenario(reference=waveform("step", dt_s=0.02, duration_s=12))
        with self.assertRaises(ValueError): Scenario(reference=waveform("step", duration_s=10))

    def test_tracking_and_settling_are_distinct(self):
        ref = waveform("sine", duration_s=12)
        with self.assertRaises(ValueError): Scenario(reference=ref)
        run = simulate(FirstOrder(), PID(), Scenario(reference=ref, recovery_mode="tracking_only"))
        result = evaluate(run)
        self.assertGreater(result["iae_rad"], 0)
        self.assertIsNone(result["recovery_time_s"])
        self.assertEqual(result["recovery_status"], "not_applicable_tracking_only")


class PhysicalModelChecks(unittest.TestCase):
    def test_undamped_free_oscillator_exact_solution(self):
        model = MassSpringDamper(damping_N_s_m=0, initial_output=0.3, initial_velocity_m_s=0.7)
        model.advance(0, 0, 0.83)
        self.assertAlmostEqual(model.output, 0.3*math.cos(2*0.83)+0.7/2*math.sin(2*0.83), places=13)
        self.assertAlmostEqual(model.velocity_m_s, -0.6*math.sin(2*0.83)+0.7*math.cos(2*0.83), places=13)

    def test_critical_damped_step_exact_solution(self):
        model = MassSpringDamper(damping_N_s_m=4)
        model.advance(4, 0, 1)
        self.assertAlmostEqual(model.output, 1-3*math.exp(-2), places=13)
        self.assertAlmostEqual(model.velocity_m_s, 4*math.exp(-2), places=13)

    def test_hold_semigroup_and_reset_both_states(self):
        for factory, kwargs in ((InductiveDCMotor, dict(initial_output=5, initial_current_A=0.3)),
                                (MassSpringDamper, dict(initial_output=0.2, initial_velocity_m_s=-0.3)),
                                (MassSpringDamper, dict(damping_N_s_m=6))):
            with self.subTest(factory=factory, kwargs=kwargs):
                a, b = factory(**kwargs), factory(**kwargs)
                a.advance(2, 0.1, 1)
                for _ in range(100): b.advance(2, 0.1, 0.01)
                self.assertAlmostEqual(a.output, b.output, places=10)
                b.reset()
                self.assertEqual(b.output, kwargs.get("initial_output", 0))
                if factory is InductiveDCMotor: self.assertEqual(b.current_A, 0.3)

    def test_motor_and_spring_disturbance_signs(self):
        for factory, sign in ((InductiveDCMotor, -1), (MassSpringDamper, 1)):
            a, b = factory(), factory()
            a.advance(1, 0, 0.5)
            b.advance(1, 0.1, 0.5)
            self.assertGreater(sign*(b.output-a.output), 0)

    def test_motor_physical_equilibrium(self):
        # 6.6 V and 0.15 N m => omega=(.66-.15)/.011, current=(6.6-.1*omega).
        y = 0.51/0.011
        model = InductiveDCMotor(initial_output=y, initial_current_A=6.6-0.1*y)
        model.advance(6.6, 0.15, 3)
        self.assertAlmostEqual(model.output, y, places=12)

    def test_physical_parameter_rejections(self):
        for factory, kwargs in ((InductiveDCMotor, dict(inductance_H=0)), (InductiveDCMotor, dict(friction_Nm_s=-1)),
                                (MassSpringDamper, dict(mass_kg=0)), (MassSpringDamper, dict(stiffness_N_m=0)),
                                (MassSpringDamper, dict(initial_velocity_m_s=float("nan")))):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): factory(**kwargs)


class NewControllerChecks(unittest.TestCase):
    def test_weight_one_reproduces_existing_pid(self):
        a = PID(kp=0.4, ki=0.8, kd=0.05, anti_windup=True)
        b = TwoDOFPID(kp=0.4, ki=0.8, kd=0.05, anti_windup=True, beta=1)
        for k in range(100):
            r, y = (10 if k < 50 else 0), math.sin(k/10)
            u, v = a.command(r, y, 0.01), b.command(r, y, 0.01)
            self.assertEqual(u, v)
            a.observe_applied(max(-2, min(2, u)))
            b.observe_applied(max(-2, min(2, v)))

    def test_weighted_pid_keeps_integral_error_and_actual_saturation(self):
        controller = TwoDOFPID(kp=10, ki=1, kd=0, beta=0, anti_windup=True)
        first = controller.command(1, 0, 0.1)
        controller.observe_applied(first)
        second = controller.command(1, 0, 0.1)
        self.assertAlmostEqual(first, 0.1)
        self.assertAlmostEqual(second, 0.2)

    def test_eso_uses_actual_applied_input(self):
        for degree, expected in ((1, 1.497), (2, 4.494)):
            controller = LinearADRC(degree, b0=2, control_bandwidth=3, observer_bandwidth=10)
            controller.command(1, 0, 0.01)
            controller.observe_applied(0.1)
            self.assertAlmostEqual(controller.command(1, 0, 0.01), expected)

    def test_eso_state_updates_are_simultaneous(self):
        controller = LinearADRC(2, b0=1, control_bandwidth=2, observer_bandwidth=10)
        controller.command(0, 0, 0.01)
        controller.observe_applied(0)
        # Sudden measurement=1 gives Euler state [0.3,3,10]; u=4*(1-.3)-4*3-10.
        self.assertAlmostEqual(controller.command(1, 1, 0.01), -19.2)

    def test_controller_reset_replay_and_grid_guard(self):
        s = scenario("measurement_noise_delay", model_spec("mass_spring_damper"))
        c, plant = LinearADRC(2), MassSpringDamper()
        a, b = simulate(plant, c, s), simulate(plant, c, s)
        self.assertEqual(a.rows, b.rows)
        with self.assertRaises(ValueError): c.command(0, 0, 0.1)
        with self.assertRaises(ValueError): LinearADRC(b0=0)
        with self.assertRaises(ValueError): TwoDOFPID(beta=1.1)


class CoverageExportChecks(unittest.TestCase):
    def test_complete_matrix_and_frozen_pairing(self):
        self.assertEqual(len(MODEL_NAMES)*len(SCENARIO_NAMES)*4, 224)
        for model in MODEL_NAMES:
            spec = model_spec(model)
            snapshots = []
            for name in SCENARIO_NAMES:
                s = scenario(name, spec)
                snapshots.append([(label, c.kp if hasattr(c, "kp") else c.b0) for label, c in controllers(spec)])
                if s.recovery_mode == "settling": self.assertTrue(s.reference.constant_after(s.recovery_start_s))
            self.assertTrue(all(x == snapshots[0] for x in snapshots))

    def test_generic_units_pairing_checksums_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "run"
            report, failed = execute(out, ("mass_spring_damper",), ("reference_sine",))
            self.assertTrue(report.is_file())
            self.assertEqual(failed, 0)
            records = [json.loads(p.read_text(encoding="utf8")) for p in (out / "runs").glob("*.json")]
            self.assertEqual(len({r["input_sha256"] for r in records}), 1)
            self.assertEqual(records[0]["units"]["output"], "m")
            with (out / records[0]["trace_file"]).open(newline="", encoding="utf8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertIn("output", rows[0])
            self.assertNotIn("true_output_rad_s", rows[0])
            self.assertEqual(rows[-1]["applied_input"], "")
            checks = json.loads((out / "checksums.json").read_text(encoding="utf8"))
            self.assertTrue(all(hashlib.sha256((out/n).read_bytes()).hexdigest() == h for n, h in checks.items()))
            with self.assertRaises(FileExistsError): execute(out)

    def test_export_failure_does_not_leave_complete_manifest(self):
        from controlstresslab.coverage import write_json
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            out = Path(temp) / "run"
            def fail_checksums(path, value):
                if path.name == "checksums.json": raise OSError("injected full disk")
                return write_json(path, value)
            with patch("controlstresslab.coverage.write_json", side_effect=fail_checksums), self.assertRaises(OSError):
                execute(out, ("first_order",), ("reference_step",))
            self.assertFalse(json.loads((out / "status.json").read_text())["artifacts_complete"])
            self.assertFalse(json.loads((out / "manifest.json").read_text())["artifacts_complete"])

    def test_incomplete_run_metrics_not_scored_as_zero(self):
        spec = model_spec("first_order")
        run = simulate(FirstOrder(), PID(), Scenario(output_bound=0.001))
        self.assertNotEqual(run.status, "completed")
        metrics = neutral_metrics(run, spec)
        self.assertIsNone(metrics["normalized_rmse"])
        self.assertIsNone(metrics["normalized_iae"])


if __name__ == "__main__": unittest.main()
