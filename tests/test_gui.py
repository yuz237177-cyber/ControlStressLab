"""Optional Qt interaction + real subprocess tests. Core-only installs skip these."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog
    from controlstresslab.gui_window import Workbench, hash_config
    from controlstresslab.gui_theme import STYLE
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

from controlstresslab.experiment import load_result, presets, execute, read_trace
from controlstresslab.benchmark_design import DEFAULT_CONFIG


@unittest.skipUnless(AVAILABLE, "optional GUI dependencies are not installed")
class DesktopChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font_dir = Path(os.environ.get("WINDIR", "C:/Windows"))/"Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc"):
            if (font_dir/name).exists(): QFontDatabase.addApplicationFont(str(font_dir/name))
        cls.app.setStyle("Fusion"); cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = Workbench(Path(self.tmp.name)/"workspace")
        self.errors = []
        self.w.error = lambda error: self.errors.append(str(error))
        self.w.show(); self.app.processEvents()

    def tearDown(self):
        if self.w.running:
            self.w.cancel_job(); self.wait_job()
        self.w.close(); self.w.deleteLater(); self.app.processEvents()
        self.tmp.cleanup()

    def wait_job(self, timeout=120):
        deadline = time.monotonic()+timeout
        while self.w.running and time.monotonic() < deadline: QTest.qWait(20)
        self.assertFalse(self.w.running, "worker did not finish")
        self.app.processEvents()

    def test_model_switch_and_profiles_edit_actual_config(self):
        self.w.model_choice.setCurrentIndex(1); self.app.processEvents()
        c = self.w.collect_config()
        self.assertEqual(c["model"], "second_order")
        self.assertIn("mass_kg", self.w.plant_boxes)
        self.w.plant_boxes["mass_kg"].setValue(1.7)
        self.w.ref_amplitude.setValue(.8)
        self.assertEqual(self.w.collect_config()["plant"]["mass_kg"], 1.7)
        self.w.profile_list.setCurrentRow(2); self.app.processEvents()
        self.assertEqual(self.w.collect_config()["conditions"]["measurement_delay_s"], .07)
        self.assertGreater(self.w.splitter.sizes()[0], self.w.splitter.sizes()[1])
        config = self.w.collect_config(); config["plant"]["gain"] = 1.23456789
        original = deepcopy(self.w.collect_config())
        with self.assertRaises(ValueError): self.w.apply_config(config)
        self.assertEqual(self.w.collect_config(), original)
        self.w.reference_kind.setCurrentIndex(self.w.reference_kind.findData("constant"))
        self.w.ref_amplitude.setValue(.6)
        from controlstresslab.experiment import scenario_for
        self.assertEqual(set(scenario_for(self.w.collect_config()).reference.values), {.6})

    def test_actual_button_run_matches_cli_and_plot_modes(self):
        self.w.apply_config(presets()[1])
        config = self.w.collect_config()
        heartbeat = []
        from PySide6.QtCore import QTimer
        timer = QTimer(); timer.timeout.connect(lambda: heartbeat.append(1)); timer.start(10)
        QTest.mouseClick(self.w.run_button, Qt.MouseButton.LeftButton)
        self.assertTrue(self.w.running)
        self.assertFalse(self.w.controls.isEnabled())
        self.wait_job(); timer.stop()
        self.assertFalse(self.errors, self.errors)
        self.assertGreater(len(heartbeat), 2)
        folder = self.w.loaded["folder"]
        self.assertEqual(self.w.loaded["verification"], "校验通过")
        self.assertEqual(len(list((folder/"figures").glob("*.png"))), 3)
        self.assertEqual(len(list((folder/"figures").glob("*.svg"))), 3)
        cli = Path(self.tmp.name)/"cli"; execute(cli, config)
        compare = load_result(cli)
        for record, reference in zip(self.w.current_records, compare["records"]):
            self.assertEqual(read_trace(folder, record), read_trace(cli, reference))
            self.assertEqual(record["metrics"], reference["metrics"])
        for mode in ("output", "error", "applied_input", "preview"):
            self.w.chart_mode.setCurrentIndex(self.w.chart_mode.findData(mode)); self.w.draw_chart()
            self.assertFalse(self.w.ax.texts, mode)
        self.w.chart_mode.setCurrentIndex(0)
        self.w.ref_amplitude.setValue(.9)
        self.assertIn("草稿已修改", self.w.chart_note.text())
        self.assertEqual(self.w.current_records[0]["scenario"]["reference"], self.w.loaded["records"][0]["scenario"]["reference"])
        destination = str(Path(self.tmp.name)/"gui.zip")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(destination, "ZIP")):
            self.w.export_report()
        self.wait_job()
        self.assertFalse(self.errors, self.errors)
        self.assertTrue(Path(destination).is_file())

    def test_cancel_and_retry_leave_distinct_experiments(self):
        QTest.mouseClick(self.w.run_button, Qt.MouseButton.LeftButton)
        cancelled = self.w.job_output
        QTest.mouseClick(self.w.run_button, Qt.MouseButton.LeftButton)
        self.wait_job()
        self.assertEqual(json.loads((cancelled/"status.json").read_text())["state"], "interrupted")
        self.assertIsNone(self.w.loaded)
        self.assertFalse(self.errors)
        QTest.mouseClick(self.w.run_button, Qt.MouseButton.LeftButton)
        self.wait_job()
        self.assertNotEqual(cancelled, self.w.job_output)
        self.assertEqual(self.w.loaded["status"]["state"], "completed")

    def test_validation_error_never_launches_worker(self):
        self.w.condition_boxes["measurement_delay_s"].setValue(.015)
        QTest.mouseClick(self.w.run_button, Qt.MouseButton.LeftButton)
        self.assertFalse(self.w.running)
        self.assertTrue(self.errors)
        self.assertFalse(list((self.w.workspace/"experiments").iterdir()))

    def test_simulation_failure_visible_with_null_metrics(self):
        self.w.config["conditions"]["output_bound"] = .001
        QTest.mouseClick(self.w.run_button, Qt.MouseButton.LeftButton)
        self.wait_job()
        self.assertFalse(self.errors, self.errors)
        self.assertEqual(self.w.loaded["status"]["state"], "completed_with_failures")
        self.assertTrue(all(r["metrics"]["rmse"] is None for r in self.w.current_records))
        self.assertTrue(all(r["metrics"]["reason"] for r in self.w.current_records))
        self.assertEqual(self.w.ax.get_xlim(), (0, 12))
        self.assertEqual(self.w.ax.lines[-1].get_xdata()[-1], 12)

    def test_saved_benchmark_viewer_and_exact_candidate_count(self):
        c = deepcopy(DEFAULT_CONFIG)
        c.update(models=["first_order"], controllers=["PI"], candidate_budget=2, heldout_seeds=[101], parameter_factors=[1])
        self.w.start_job("benchmark", c); self.wait_job()
        self.assertFalse(self.errors, self.errors)
        self.assertEqual(self.w.loaded["status"]["written_runs"], 14)
        self.assertGreater(self.w.case_selector.count(), 1)
        for index in range(self.w.case_selector.count()):
            self.w.case_selector.setCurrentIndex(index); self.w.draw_chart()
            self.assertFalse(self.w.ax.texts)
        self.assertEqual({r["phase"] for r in self.w.current_records}, {"baseline", "tuned"})

    def test_saved_config_roundtrip_and_tampered_results_disable_export(self):
        config = self.w.collect_config(); path = Path(self.tmp.name)/"config.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "JSON")):
            self.w.save_config()
        self.assertEqual(json.loads(path.read_text(encoding="utf8")), config)
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
            self.w.import_config()
        self.assertEqual(hash_config(self.w.collect_config()), hash_config(config))
        folder = Path(self.tmp.name)/"old"; execute(folder, config)
        (folder/"runs/PI.csv").write_text("damaged")
        self.w.open_result(folder)
        self.assertFalse(self.w.export_button.isEnabled())
        self.assertIn("校验不一致", self.w.chart_note.text())


if __name__ == "__main__": unittest.main()
