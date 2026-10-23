"""Regression tests for the reviewed failure, recording and event-window contracts."""

from dataclasses import replace
import csv
import contextlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from controlstresslab import DCMotor, FirstOrder, PID, Scenario, StepSignal, simulate
from controlstresslab.cli import demo_scenarios, execute_demo
from controlstresslab.metrics import evaluate


class Constant:
    def reset(self):
        pass

    def command(self, reference, measurement, dt):
        return 0.0

    def observe_applied(self, applied):
        pass


class FailCommand(Constant):
    def __init__(self, exception=TypeError, at=0):
        self.exception, self.at = exception, at

    def reset(self):
        self.calls = 0

    def command(self, reference, measurement, dt):
        count = self.calls
        self.calls += 1
        if count == self.at:
            raise self.exception("injected failure")
        return 1.0


class FailureRecording(unittest.TestCase):
    def test_controller_failure_preserves_current_state_and_time(self):
        run = simulate(FirstOrder(), FailCommand(at=4), Scenario(dt_s=0.1))
        self.assertEqual(run.status, "interface_error")
        self.assertEqual(run.failure["phase"], "controller.command")
        self.assertAlmostEqual(run.rows[-1]["time_s"], 0.4)
        self.assertAlmostEqual(run.last_integrated_time_s, 0.4)
        self.assertAlmostEqual(evaluate(run)["observed_until_s"], 0.4)
        self.assertEqual(run.rows[-1]["interval_s"], 0.0)
        self.assertFalse(run.rows[-1]["action_taken"])
        self.assertIsNone(run.rows[-1]["command_V"])
        self.assertIn("TypeError", run.failure["traceback"])

    def test_failed_advance_does_not_claim_a_completed_interval(self):
        class BadPlant(FirstOrder):
            def advance(self, u, disturbance, dt):
                raise ValueError("could not integrate")
        run = simulate(BadPlant(), Constant(), Scenario())
        self.assertEqual(run.status, "numerical_failure")
        self.assertEqual(run.failure["phase"], "plant.advance")
        self.assertTrue(run.rows[-1]["action_taken"])
        self.assertFalse(run.rows[-1]["transition_completed"])
        self.assertEqual(run.rows[-1]["interval_s"], 0.0)
        self.assertEqual(run.last_integrated_time_s, 0.0)
        self.assertIsNone(evaluate(run)["iae_post_event_rad"])

    def test_reset_failure_has_diagnostics_and_no_fake_trace(self):
        class BadReset(Constant):
            def reset(self):
                raise ValueError("bad reset")
        run = simulate(DCMotor(), BadReset(), Scenario())
        self.assertEqual(run.status, "interface_error")
        self.assertEqual(run.failure["phase"], "controller.reset")
        self.assertEqual(run.rows, [])

    def test_invalid_controller_return_is_interface_error(self):
        class Missing(Constant):
            def command(self, reference, measurement, dt):
                return None
        run = simulate(DCMotor(), Missing(), Scenario())
        self.assertEqual(run.status, "interface_error")
        self.assertEqual(run.failure["type"], "TypeError")

    def test_nonfinite_command_has_numeric_classification_and_safe_record(self):
        class Nonfinite(Constant):
            def command(self, reference, measurement, dt):
                return float("inf")
        run = simulate(DCMotor(), Nonfinite(), Scenario())
        self.assertEqual(run.status, "numerical_failure")
        json.dumps(run.rows, allow_nan=False)
        self.assertIsNone(run.rows[-1]["command_V"])

    def test_nonfinite_measurement_is_rejected_before_controller(self):
        scenario = Scenario(reference=StepSignal(((0.0, 0.0),)), noise_std=1.7e308)
        run = simulate(DCMotor(), Constant(), scenario)
        self.assertEqual(run.status, "numerical_failure")
        self.assertEqual(run.failure["phase"], "measurement")
        self.assertIsNone(run.rows[-1]["measurement_rad_s"])
        self.assertFalse(run.rows[-1]["action_taken"])
        json.dumps(run.rows, allow_nan=False)

    def test_fail_fast_keeps_original_exception(self):
        with self.assertRaisesRegex(KeyError, "injected"):
            simulate(DCMotor(), FailCommand(KeyError), Scenario(), fail_fast=True)

    def test_user_interrupt_propagates(self):
        with self.assertRaises(KeyboardInterrupt):
            simulate(DCMotor(), FailCommand(KeyboardInterrupt), Scenario())

    def test_non_numeric_plant_output_is_interface_error(self):
        class TextPlant:
            output = "not a state"
            def reset(self):
                pass
        run = simulate(TextPlant(), Constant(), Scenario())
        self.assertEqual(run.status, "interface_error")
        self.assertEqual(run.failure["phase"], "plant.output")


class ConfigurationAndMetadata(unittest.TestCase):
    def test_unreasonably_large_sample_count_is_rejected_before_allocation(self):
        with self.assertRaisesRegex(ValueError, "sample count"):
            Scenario(dt_s=1e-6)

    def test_models_reject_nonfinite_inputs(self):
        for plant in (FirstOrder(), DCMotor()):
            with self.subTest(plant=type(plant).__name__), self.assertRaises(ValueError):
                plant.advance(1.0, float("nan"), 0.01)

    def test_derived_motor_rate_is_validated(self):
        with self.assertRaises(ValueError):
            DCMotor(back_emf_V_s=1e308)

    def test_custom_configuration_is_captured_before_reset(self):
        class Configured(Constant):
            gain = 3.7
            def to_config(self):
                return {"gain": self.gain}
            def reset(self):
                self.gain = 99
        run = simulate(DCMotor(), Configured(), Scenario())
        self.assertEqual(run.controller["gain"], 3.7)
        self.assertTrue(run.controller["params_recorded"])

    def test_missing_config_is_explicit(self):
        run = simulate(DCMotor(), Constant(), Scenario())
        self.assertFalse(run.controller["params_recorded"])
        self.assertIn("controller_parameters_not_recorded", run.diagnostics)

    def test_nonserializable_config_is_explicit_interface_failure(self):
        class BadConfig(Constant):
            def to_config(self):
                return {"bad": {1, 2}}
        run = simulate(DCMotor(), BadConfig(), Scenario())
        self.assertEqual(run.status, "interface_error")
        self.assertEqual(run.failure["phase"], "metadata")

    def test_delay_equal_to_duration_is_marked(self):
        run = simulate(DCMotor(), Constant(), Scenario(measurement_delay_s=12.0))
        self.assertIn("no_live_measurement_during_control", run.diagnostics)


class EventMetrics(unittest.TestCase):
    def test_event_parts_sum_to_original_full_window(self):
        scenario = next(s for s in demo_scenarios(0.01, 42) if s.name == "load_step")
        values = evaluate(simulate(DCMotor(), PID(), scenario))
        self.assertAlmostEqual(values["iae_pre_event_rad"], 31.787683240000042, places=10)
        self.assertAlmostEqual(values["iae_post_event_rad"], 2.111435327641525, places=10)
        self.assertAlmostEqual(values["iae_rad"], values["iae_pre_event_rad"] + values["iae_post_event_rad"], places=10)
        self.assertAlmostEqual(values["pre_event_duration_s"] + values["post_event_duration_s"], 11.5)

    def test_empty_pre_event_window_is_null_not_zero(self):
        values = evaluate(simulate(DCMotor(), PID(), Scenario()))
        self.assertIsNone(values["iae_pre_event_rad"])
        self.assertEqual(values["pre_event_duration_s"], 0.0)
        self.assertAlmostEqual(values["iae_post_event_rad"], values["iae_rad"])

    def test_recovery_scans_beyond_initial_in_band_sample(self):
        scenario = Scenario()
        run = simulate(DCMotor(), Constant(), scenario)
        for row in run.rows:
            row["true_output_rad_s"] = row["reference_rad_s"]
        run.rows[200]["true_output_rad_s"] = 0.0
        self.assertAlmostEqual(evaluate(run)["recovery_time_s"], 1.51)


class BatchAndExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "outputs").mkdir(exist_ok=True)

    def test_endpoint_exports_blank_input_and_explicit_action_flags(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary:
            target = Path(temporary) / "demo"
            execute_demo(target)
            with (target / "nominal__pid__seed42.csv").open(encoding="utf8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[-1]["applied_V"], "")
            self.assertEqual(rows[-1]["command_V"], "")
            self.assertEqual(rows[-1]["action_taken"], "False")
            self.assertEqual(rows[-1]["transition_completed"], "False")
            document = (target / "report.html").read_text(encoding="utf8")
            self.assertIn("控制器可见测量", document)
            self.assertIn("实际输入", document)
            self.assertEqual(document.count('<svg role="img"'), 30)

    def test_batch_stops_and_keeps_failed_record_by_default(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.PID", side_effect=lambda **kw: FailCommand()):
            target = Path(temporary) / "failed"
            execute_demo(target)
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf8"))
            self.assertEqual(manifest["batch_status"], "stopped_on_failure")
            self.assertEqual(manifest["written_runs"], 1)
            self.assertEqual(manifest["runs"][0]["failure"]["type"], "TypeError")
            self.assertTrue((target / "report.html").is_file())

    def test_explicit_continue_records_all_failures(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.PID", side_effect=lambda **kw: FailCommand()):
            target = Path(temporary) / "continued"
            execute_demo(target, continue_on_failure=True)
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf8"))
            self.assertEqual(manifest["batch_status"], "completed_with_failures")
            self.assertEqual(manifest["failed_runs"], 10)

    def test_interrupt_marks_batch_and_remains_an_interrupt(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.PID", side_effect=lambda **kw: FailCommand(KeyboardInterrupt)):
            target = Path(temporary) / "interrupted"
            with self.assertRaises(KeyboardInterrupt):
                execute_demo(target)
            self.assertEqual(json.loads((target / "status.json").read_text())["state"], "interrupted")

    def test_writer_error_marks_aborted_batch(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.write_csv", side_effect=OSError("injected write failure")):
            target = Path(temporary) / "aborted"
            with self.assertRaises(OSError):
                execute_demo(target)
            status = json.loads((target / "status.json").read_text())
            self.assertEqual(status["state"], "aborted")
            self.assertEqual(status["error_type"], "OSError")


class ArtifactFinalization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "outputs").mkdir(exist_ok=True)

    def test_report_write_failure_cannot_leave_completed_manifest(self):
        original = Path.write_text
        def fail_report(path, *args, **kwargs):
            if path.name == "report.html":
                raise OSError("report unavailable")
            return original(path, *args, **kwargs)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch.object(Path, "write_text", fail_report):
            target = Path(temporary) / "demo"
            with self.assertRaisesRegex(OSError, "report unavailable"):
                execute_demo(target)
            status = json.loads((target / "status.json").read_text())
            self.assertEqual(status["state"], "aborted")
            self.assertFalse(status["artifacts_complete"])
            self.assertFalse((target / "manifest.json").exists())
            self.assertEqual((status["expected_runs"], status["written_runs"], status["failed_runs"]), (10, 10, 0))

    def test_checksums_failure_keeps_uncommitted_status_and_updates_manifest(self):
        from controlstresslab.cli import write_json
        def fail_checksums(path, value):
            if path.name == "checksums.json":
                current = json.loads((path.parent / "status.json").read_text())
                self.assertEqual(current["state"], "in_progress")
                self.assertFalse(current["artifacts_complete"])
                raise OSError("checksum unavailable")
            return write_json(path, value)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.write_json", side_effect=fail_checksums):
            target = Path(temporary) / "demo"
            with self.assertRaisesRegex(OSError, "checksum unavailable"):
                execute_demo(target)
            self.assertEqual(json.loads((target / "status.json").read_text())["state"], "aborted")
            self.assertEqual(json.loads((target / "manifest.json").read_text())["batch_status"], "aborted")

    def test_final_status_is_written_only_after_checksums_exist(self):
        from controlstresslab.cli import write_json
        def inspect_commit(path, value):
            if path.name == "status.json" and value["artifacts_complete"]:
                self.assertTrue((path.parent / "checksums.json").is_file())
                raise OSError("commit unavailable")
            return write_json(path, value)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.write_json", side_effect=inspect_commit):
            target = Path(temporary) / "demo"
            with self.assertRaisesRegex(OSError, "commit unavailable"):
                execute_demo(target)
            status = json.loads((target / "status.json").read_text())
            self.assertEqual(status["state"], "aborted")
            self.assertFalse(status["artifacts_complete"])

    def test_system_exit_keeps_code_and_stable_status_fields(self):
        class ExitController(Constant):
            def command(self, reference, measurement, dt):
                raise SystemExit(3)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.PID", side_effect=lambda **kw: ExitController()):
            target = Path(temporary) / "demo"
            with self.assertRaises(SystemExit) as raised:
                execute_demo(target)
            self.assertEqual(raised.exception.code, 3)
            status = json.loads((target / "status.json").read_text())
            self.assertEqual(status["state"], "interrupted")
            self.assertEqual(status["error_type"], "SystemExit")
            self.assertEqual(set(status), {"schema_version", "state", "expected_runs", "written_runs", "failed_runs", "artifacts_complete", "error_type", "message"})

    def test_failed_cli_does_not_announce_success(self):
        from controlstresslab.cli import main
        output = io.StringIO()
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.PID", side_effect=lambda **kw: FailCommand()):
            with patch.object(sys, "argv", ["controlstresslab", "--output", str(Path(temporary) / "demo")]), contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main()
            self.assertEqual(raised.exception.code, 1)
            self.assertIn("1 failed runs", output.getvalue())
            self.assertNotIn("Synthetic demo complete:", output.getvalue())

    def test_metric_failure_reaches_manifest_report_and_cli_exit(self):
        from controlstresslab.cli import main
        scenario = Scenario(dt_s=0.1, duration_s=1.0, evaluation_start_s=0, recovery_start_s=0,
                            reference=StepSignal(((0.0, 1e308),)))
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary, patch("controlstresslab.cli.demo_scenarios", return_value=[scenario]), patch("controlstresslab.cli.PID", side_effect=lambda **kw: Constant()):
            target = Path(temporary) / "demo"
            with patch.object(sys, "argv", ["controlstresslab", "--output", str(target)]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main()
            self.assertEqual(raised.exception.code, 1)
            manifest = json.loads((target / "manifest.json").read_text())
            metrics = manifest["runs"][0]["metrics"]
            self.assertEqual(metrics["status"], "metric_failure")
            self.assertIsNone(metrics["iae_rad"])
            self.assertIn("metric_failure", (target / "report.html").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
