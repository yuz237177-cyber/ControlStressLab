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
        self.assertEqual(json.loads((cancelled/"status.json").read_text(encoding="utf8"))["state"], "interrupted")
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

    def test_scan_button_heatmap_click_worst_case_and_config_roundtrip(self):
        from controlstresslab.robustness import run_count
        from matplotlib.backend_bases import MouseEvent
        self.w.switch_page(3)
        page = self.w.scan_page
        page.x_values.setText("0.5, 1.5")
        page.y_values.setText("0, 0.05")
        page.seeds.setText("11,22")
        config = page.validate_plan()
        self.assertEqual(run_count(config),16)
        path = Path(self.tmp.name)/"scan-config.json"
        with patch.object(QFileDialog,"getSaveFileName",return_value=(str(path),"JSON")):
            page.save_config()
        self.assertEqual(json.loads(path.read_text(encoding="utf8")),config)
        page.x_values.setText("2")
        with patch.object(QFileDialog,"getOpenFileName",return_value=(str(path),"JSON")):
            page.import_config()
        self.assertEqual(page.config(),config)
        QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton)
        self.wait_job()
        self.assertFalse(self.errors,self.errors)
        self.assertEqual(self.w.pages.currentIndex(),3)
        self.assertEqual(len(self.w.loaded["records"]),16)
        self.assertEqual(self.w.loaded["verification"],"校验通过")
        self.assertEqual(len(list((self.w.loaded["folder"]/"figures").glob("*.png"))),10)
        page.canvas.draw()
        x,y = page.ax.transData.transform((1,0))
        event = MouseEvent("button_press_event",page.canvas,x,y,button=1)
        page.canvas.callbacks.process("button_press_event",event)
        self.app.processEvents()
        self.assertEqual(self.w.pages.currentIndex(),0)
        self.assertEqual({tuple(r["axis_indices"]) for r in self.w.current_records},{(1,0)})
        self.assertEqual({r["seed"] for r in self.w.current_records},{11})
        self.assertEqual(len(self.w.current_records),2)
        self.w.switch_page(3);page.locate_worst()
        self.assertEqual(self.w.pages.currentIndex(),0)
        self.assertTrue(all(r["metrics"]["rmse"] is not None for r in self.w.current_records))

    def test_scan_cancel_preserves_partial_status(self):
        self.w.switch_page(3)
        QTest.mouseClick(self.w.scan_page.start_button,Qt.MouseButton.LeftButton)
        folder = self.w.job_output
        QTest.mouseClick(self.w.run_button,Qt.MouseButton.LeftButton)
        self.wait_job()
        self.assertFalse(self.errors,self.errors)
        status = json.loads((folder/"status.json").read_text(encoding="utf8"))
        self.assertEqual(status["state"],"interrupted")
        self.assertFalse(status["artifacts_complete"])

    def test_cross_experiment_overlay_and_independent_snapshot(self):
        paths = [Path(self.tmp.name)/"A",Path(self.tmp.name)/"B"]
        c = self.w.collect_config()
        execute(paths[0],c)
        c["conditions"]["noise_std"] = .02;execute(paths[1],c)
        self.w.switch_page(4)
        page = self.w.comparison_page
        page.add_source(paths[0],case_id="PID_aw",label="干净基线")
        page.add_source(paths[1],case_id="PID_aw",label="加入噪声")
        self.assertTrue(page.save_button.isEnabled())
        self.assertIn("conditions.noise_std",page.diffs.text())
        self.assertEqual(len(page.figure.axes[0].lines),3)
        QTest.mouseClick(page.save_button,Qt.MouseButton.LeftButton)
        self.wait_job()
        self.assertFalse(self.errors,self.errors)
        self.assertEqual(self.w.pages.currentIndex(),4)
        loaded = self.w.loaded
        self.assertEqual(loaded["verification"],"校验通过")
        self.assertEqual(len(list((loaded["folder"]/"figures").glob("*.svg"))),3)
        self.assertEqual(len(self.w.record_groups),1)
        self.assertEqual(len(self.w.current_records),2)
        for i,r in enumerate(loaded["records"]):
            source = next(r for r in load_result(paths[i])["records"] if r["case_id"] == "PID_aw")
            self.assertEqual(r["metrics"],source["metrics"])
        for key in ("output","error","applied_input"):
            page.channel.setCurrentIndex(page.channel.findData(key));page.draw()
            self.assertFalse(page.figure.axes[0].texts)

    def test_comparison_export_rechecks_source_after_cached_preview(self):
        paths = [Path(self.tmp.name)/"A",Path(self.tmp.name)/"B"]
        c = self.w.collect_config()
        for p in paths: execute(p,c)
        page = self.w.comparison_page
        for i,p in enumerate(paths): page.add_source(p,case_id="PID_aw",label=str(i))
        self.assertTrue(page.current)
        path = paths[1]/"runs/PID_aw.csv";path.write_bytes(path.read_bytes()+b"changed")
        page.save();self.wait_job()
        self.assertTrue(self.errors)
        self.assertTrue(any("校验" in error for error in self.errors))
        self.assertFalse(self.w.job_output.exists())


    def test_drawers_preserve_configuration_and_initial_preview_is_real(self):
        before = deepcopy(self.w.collect_config())
        self.assertGreater(len(self.w.figure.axes[0].lines), 0)
        original_height = self.w.canvas.height()
        QTest.mouseClick(self.w.parameter_drawer.toggle, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertTrue(self.w.parameter_drawer.scroll.isVisible())
        self.assertEqual(self.w.collect_config(), before)
        self.assertLess(self.w.canvas.height(), original_height)
        QTest.mouseClick(self.w.parameter_drawer.toggle, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(self.w.collect_config(), before)
        self.assertGreaterEqual(self.w.canvas.height(), original_height)
        QTest.mouseClick(self.w.library_button, Qt.MouseButton.LeftButton)
        self.assertTrue(self.w.library.isVisible())
        QTest.mouseClick(self.w.library_button, Qt.MouseButton.LeftButton)
        self.assertFalse(self.w.library.isVisible())

    def tuning_small(self):
        from controlstresslab.tuning_protocol import default_config
        c=default_config();c["candidate_budget"]=2;c["thresholds"]["saturation_max"]=1
        c["search"]["axes"]=c["search"]["axes"][:1];c["search"]["axes"][0]["values"]=[1.]
        c["search"]["families"]=c["search"]["families"][:1];c["search"]["seeds"]=[11]
        c["validation"]["points"]=[{"plant.tau_s":.9}];c["validation"]["families"]=c["validation"]["families"][:1]
        c["validation"]["seeds"]=[22];c["validation"]["waveform_seeds"]=[33]
        return c

    def test_tuning_buttons_complete_search_freeze_validate_and_keep_ui_alive(self):
        page=self.w.tuning_page;page.set_config(self.tuning_small())
        self.w.switch_page(1);self.w.tuning_tabs.setCurrentIndex(1)
        from PySide6.QtCore import QTimer
        beats=[];timer=QTimer();timer.timeout.connect(lambda:beats.append(1));timer.start(10)
        QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton)
        self.assertFalse(page.editor.isEnabled());self.wait_job();timer.stop()
        self.assertFalse(self.errors,self.errors);self.assertGreater(len(beats),2)
        self.assertEqual(self.w.tuning_tabs.currentIndex(),1)
        self.assertEqual(len(page.loaded["records"]),2)
        self.assertTrue(page.freeze_button.isEnabled());self.assertFalse(page.validate_button.isEnabled())
        page.main_choice.setCurrentIndex(page.main_choice.findData(1))
        QTest.mouseClick(page.freeze_button,Qt.MouseButton.LeftButton);self.wait_job()
        self.assertFalse(self.errors,self.errors)
        self.assertTrue(page.validate_button.isEnabled());self.assertFalse(page.freeze_button.isEnabled())
        receipt=(page.selection_folder/"selection.json").read_bytes()
        QTest.mouseClick(page.validate_button,Qt.MouseButton.LeftButton);self.wait_job()
        self.assertFalse(self.errors,self.errors)
        self.assertEqual(page.summary["main_candidate_id"],1)
        self.assertFalse(page.summary["validation_ranking_allowed"])
        self.assertEqual(self.w.loaded["verification"],"校验通过")
        self.assertEqual(receipt,(page.loaded["folder"]/"evidence/selection/selection.json").read_bytes())
        self.assertTrue(self.w.export_button.isEnabled())
        for key in ("requirements","output","error","applied_input"):
            page.channel.setCurrentIndex(page.channel.findData(key));page.draw()
            self.assertTrue(page.figure.axes)

    def test_tuning_candidate_row_identity_diagnosis_and_send_to_experiment(self):
        from controlstresslab.tuning import execute as search
        folder=Path(self.tmp.name)/"tuning";search(folder,self.tuning_small())
        self.w.open_result(folder);page=self.w.tuning_page
        page.table.setSortingEnabled(True);page.table.sortItems(0,Qt.SortOrder.DescendingOrder)
        cid=page.table.item(0,0).data(Qt.ItemDataRole.UserRole)
        page.choose_table(0,0);self.assertEqual(page.candidate.currentData(),cid)
        page.choose_case(0,0);self.assertEqual(page.channel.currentData(),"output")
        record=next(r for r in page.loaded["records"] if r["case_id"]==page.case.currentData())
        page.send_to_experiment();c=self.w.collect_config()
        self.assertEqual(c["selected_controllers"],["PID_aw"])
        expected=next(d["parameters"] for d in record["run_config"]["controllers"] if d["name"]=="PID_aw")
        # The experiment editor explicitly refuses parameter precision it cannot retain.
        if self.errors:self.assertIn("精度",self.errors[-1])
        else:self.assertEqual(next(d["parameters"] for d in c["controllers"] if d["name"]=="PID_aw"),expected)

    def test_tuning_no_feasible_and_corrupt_results_cannot_freeze(self):
        from controlstresslab.tuning import execute as search
        folder=Path(self.tmp.name)/"none";c=self.tuning_small();c["thresholds"]["error_max"]=0
        search(folder,c);self.w.open_result(folder);page=self.w.tuning_page
        self.assertEqual(page.summary["feasible_count"],0)
        self.assertFalse(page.freeze_button.isEnabled());self.assertFalse(page.validate_button.isEnabled())
        with (folder/"summary.json").open("a",encoding="utf8") as stream:stream.write(" ")
        self.w.open_result(folder)
        self.w.set_running(True);self.w.set_running(False)
        self.assertFalse(page.freeze_button.isEnabled());self.assertFalse(page.validate_button.isEnabled())



    def test_custom_model_editor_send_roundtrip_and_explicit_no_disturbance(self):
        from controlstresslab.experiment import default_config
        page=self.w.model_page;self.w.switch_page(5)
        page.templates.setCurrentIndex(page.templates.findData("fourth_order"));page.use_template()
        page.name.setText("四阶中文模型")
        page.dt.setText("0.03");page.duration.setText("3")
        expected=page.plant()
        page.send();self.app.processEvents()
        self.assertFalse(self.errors,self.errors)
        c=self.w.collect_config()
        self.assertEqual(c["plant"],expected)
        self.assertEqual(c["conditions"],default_config("transfer_function")["conditions"])
        self.assertFalse(self.w.controller_checks["LADRC"].isEnabled())
        self.w.edit_model();self.assertEqual(page.plant(),expected)
        self.assertIn("4阶",page.formula.text())
        destination=Path(self.tmp.name)/"中文模型.json"
        with patch.object(QFileDialog,"getSaveFileName",return_value=(str(destination),"JSON")):page.save_model()
        saved=json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(saved["plant"],expected)
        page.templates.setCurrentIndex(page.templates.findData("integrator"));page.use_template()
        with patch.object(QFileDialog,"getOpenFileName",return_value=(str(destination),"JSON")):page.import_model()
        self.assertEqual(page.plant(),expected)
        page.dist_enabled.setChecked(False);page.send()
        self.assertFalse(self.errors,self.errors)
        c=self.w.collect_config()
        self.assertIsNone(c["plant"]["disturbance_numerator"])
        self.assertEqual(c["disturbance"]["offset"],0)

    def test_custom_model_worker_preview_closed_loop_and_original_preview_immutable(self):
        page=self.w.model_page;self.w.switch_page(5)
        page.templates.setCurrentIndex(page.templates.findData("integrator"));page.use_template()
        page.duration.setText("2");page.dt.setText("0.02")
        QTest.mouseClick(page.preview_button,Qt.MouseButton.LeftButton)
        self.assertTrue(self.w.running);self.assertFalse(page.editor.isEnabled())
        self.wait_job();self.assertFalse(self.errors,self.errors)
        loaded=self.w.loaded;folder=loaded["folder"]
        self.assertEqual(loaded["verification"],"校验通过")
        before=(folder/"model-snapshot.json").read_bytes()
        self.assertEqual(len(list((folder/"figures").glob("*"))),2)
        self.assertTrue(page.figure.axes)
        page.numerator.setText("2")
        self.assertIn("草稿已修改",page.note.text())
        self.assertEqual((folder/"model-snapshot.json").read_bytes(),before)
        page.send()
        QTest.mouseClick(self.w.run_button,Qt.MouseButton.LeftButton);self.wait_job()
        self.assertFalse(self.errors,self.errors)
        self.assertEqual(self.w.loaded["verification"],"校验通过")
        self.assertTrue(self.w.current_records)
        self.assertEqual((folder/"model-snapshot.json").read_bytes(),before)
        self.w.open_result(folder)
        self.assertEqual(page.plant()["numerator"],[1.])
        self.assertFalse(self.w.current_records)

    def test_custom_model_invalid_preview_does_not_launch_worker(self):
        page=self.w.model_page
        page.numerator.setText("1,1")
        page.preview()
        self.assertFalse(self.w.running);self.assertTrue(self.errors)
        self.assertFalse(list(self.w.workspace.rglob("preview.csv")))



    def test_frequency_worker_uses_frozen_case_and_rejects_later_source_edits(self):
        from controlstresslab.experiment import default_config
        c=default_config();folder=Path(self.tmp.name)/"frequency-source";execute(folder,c)
        self.w.open_result(folder);page=self.w.frequency_page;page.from_saved()
        self.w.switch_page(6);page.start();self.wait_job()
        self.assertFalse(self.errors,self.errors)
        self.assertEqual(self.w.loaded["manifest"]["schema_version"],"frequency-1.0")
        self.assertTrue(all(r["summary"]["time_check"]["state"]=="passed" for r in page.records))
        self.assertEqual(self.w.loaded["verification"],"校验通过")
        for key in ("poles","sensitivity","channels","bode"):
            page.mode.setCurrentIndex(page.mode.findData(key));self.app.processEvents()
            self.assertTrue(page.figure.axes)
        page.high.setText("1000");page.start()
        self.assertFalse(self.w.running);self.assertTrue(self.errors)

    def test_project_home_creates_tracks_and_migrates_using_background_workers(self):
        page=self.w.project_page;page.title.setText("桌面项目");page.create()
        original=self.w.active_project;self.assertTrue((original/"project.json").exists())
        self.w.start_job("experiment",self.w.collect_config());self.wait_job()
        self.assertFalse(self.errors,self.errors);self.assertEqual(page.table.rowCount(),1)
        archive=Path(self.tmp.name)/"project.cslproj"
        with patch.object(QFileDialog,"getSaveFileName",return_value=(str(archive),"项目包")):page.export()
        self.wait_job();self.assertFalse(self.errors,self.errors);self.assertTrue(archive.is_file())
        with patch.object(QFileDialog,"getOpenFileName",return_value=(str(archive),"项目包")):page.import_bundle()
        self.wait_job();self.assertFalse(self.errors,self.errors)
        self.assertNotEqual(self.w.active_project,original);self.assertEqual(page.table.rowCount(),1)
        page.leave();self.assertIsNone(self.w.active_project)

if __name__ == "__main__": unittest.main()
