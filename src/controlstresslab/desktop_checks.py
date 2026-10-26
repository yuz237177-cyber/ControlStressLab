"""Real desktop acceptance for both source and frozen builds; no network."""
from copy import deepcopy
import json,os,sys,time,uuid
from pathlib import Path

def run(w,report):
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from . import __version__
    from . import frequency,projects,robustness,tuning_protocol
    from .experiment import atomic_json,default_config,load_result
    report=Path(report).resolve();report.parent.mkdir(parents=True,exist_ok=True)
    screenshots=[];errors=[];beats=[];folders={};workers=[]
    w.error=lambda e:errors.append(str(e))
    timer=QTimer(w);timer.timeout.connect(lambda:beats.append(time.monotonic()));timer.start(30)
    def wait():
        end=time.monotonic()+240
        while w.running and time.monotonic()<end:QTest.qWait(30)
        if w.running:raise TimeoutError("桌面后台任务超时")
        if errors:raise AssertionError(errors)
        runtime=w.last_event.get("runtime",{})
        assert runtime.get("frozen")==bool(getattr(sys,"frozen",False)),runtime
        workers.append(dict(kind=w.job_kind,**runtime))
        QTest.qWait(70)
    def shot(name):
        QTest.qWait(150);path=report.parent/(report.stem+"-"+name+".png")
        assert w.grab().save(str(path));screenshots.append(str(path))
    try:
        w.resize(1560,1000)
        # Load complete bundled first-order example by the actual GUI action.
        w.project_page.examples.setCurrentIndex(0);w.project_page.example();wait()
        assert w.active_project is not None
        folders["bundled_example"]=str(w.active_project);shot("project")
        p=w.model_page;w.switch_page(5);p.templates.setCurrentIndex(p.templates.findData("second_order"));p.use_template()
        p.duration.setText("12");p.preview();wait();folders["preview"]=str(w.loaded["folder"])
        p.drawer.set_expanded(False);shot("model")
        p.send();c=w.collect_config();c["selected_controllers"]=["PI","PID_aw","TwoDOF_PID"]
        c["conditions"].update(dt_s=.02,noise_std=.005,measurement_delay_s=.02)
        for d in c["controllers"]:
            if d["name"]!="LADRC":
                d["parameters"].update(kp=1.,ki=.5)
                if d["name"]!="PI":d["parameters"]["kd"]=.3
        w.apply_config(c);w.parameter_drawer.set_expanded(False);w.start_job("experiment",c);wait()
        folders["experiment"]=str(w.loaded["folder"]);assert len(w.current_records)==3;shot("response")
        page=w.frequency_page;page.from_saved();w.switch_page(6);page.start();wait()
        folders["frequency"]=str(w.loaded["folder"]);shot("frequency")
        assert all(r["summary"]["time_check"]["state"]=="passed" for r in page.records)
        for mode in ("poles","sensitivity","channels","bode"):page.mode.setCurrentIndex(page.mode.findData(mode));QTest.qWait(30)
        scan=robustness.default_config(c);scan["axes"]=[dict(key="plant.time_scale",values=[.9,1.1])]
        w.start_job("robustness",scan);wait();folders["scan"]=str(w.loaded["folder"])
        tc=tuning_protocol.default_config(c);tc["candidate_budget"]=2
        tc["ranges"]=dict(kp=dict(low=.8,high=1.2,scale="linear"),ki=dict(low=.3,high=.5,scale="linear"),kd=dict(low=.1,high=.3,scale="linear"))
        tc["thresholds"]=dict(error_max=None,saturation_max=1.,variation_max=None)
        tc["search"]["axes"]=tc["search"]["axes"][:1];tc["search"]["families"]=tc["search"]["families"][:1];tc["search"]["seeds"]=[51911]
        key=tc["search"]["axes"][0]["key"]
        tc["validation"]["points"]=[{key:.97}];tc["validation"]["families"]=tc["validation"]["families"][:1]
        tc["validation"]["seeds"]=[51922];tc["validation"]["waveform_seeds"]=[51933]
        # Distinct input seeds and waves from bundled demonstration cases.
        tc["validation"]["families"][0]["reference"]["amplitude"]=.73
        w.tuning_page.set_config(tc);w.start_job("tuning_search",tc);wait()
        folders["search"]=str(w.loaded["folder"]);t=w.tuning_page
        t.main_choice.setCurrentIndex(t.main_choice.findData(1));t.rationale.setText("冻结候选1作为主选；以事先声明的独立波形工况验证，不用验证结果重新排名。")
        t.freeze();wait();folders["selection"]=str(w.loaded["folder"])
        receipt=(w.loaded["folder"]/"selection.json").read_bytes()
        t.validate();wait();folders["validation"]=str(w.loaded["folder"]);shot("validation")
        project=w.active_project;projects.read(project)
        bundle=report.parent/(report.stem+".cslproj")
        w.start_job("project_export",dict(folder=str(project),destination=str(bundle)));wait()
        project.rename(project.with_name(project.name+"-original-unavailable"))
        destination=w.workspace/"projects"/("relocated-"+uuid.uuid4().hex[:8])
        w.start_job("project_import",dict(archive=str(bundle),destination=str(destination)));wait()
        folders["relocated_project"]=str(destination)
        selection=destination/"results"/Path(folders["selection"]).name
        assert (selection/"selection.json").read_bytes()==receipt
        w.open_result(selection);t.validate();wait()
        assert json.loads((w.loaded["folder"]/"manifest.json").read_text(encoding="utf-8"))["observation"]=="reproduction_same_frozen_selection"
        w.open_result(destination/"results"/Path(folders["frequency"]).name)
        w.frequency_page.start();wait();folders["relocated_frequency"]=str(w.loaded["folder"])
        w.project_page.refresh();w.switch_page(7);shot("relocated")
        w.resize(1120,780);w.switch_page(6);shot("compact")
        assert len(beats)>10
        atomic_json(report,dict(passed=True,version=__version__,frozen=bool(getattr(sys,"frozen",False)),executable=sys.executable,
            dpr=w.devicePixelRatioF(),heartbeat_count=len(beats),errors=errors,folders=folders,screenshots=screenshots,workers=workers,sys_path=sys.path,prefix=sys.prefix,
            runtime_isolation=dict(PATH=os.environ.get("PATH",""),PYTHONPATH=os.environ.get("PYTHONPATH","")),
            scope="real local Windows desktop; isolated runtime paths; not a separate pristine Windows VM"))
        timer.stop();w.close();QApplication.instance().exit(0)
    except BaseException as exc:
        import traceback
        atomic_json(report,dict(passed=False,errors=errors,error=str(exc),traceback=traceback.format_exc(),screenshots=screenshots,folders=folders))
        timer.stop()
        if w.running:w.process.kill();QTest.qWait(300);w.set_running(False)
        w.close();QApplication.instance().exit(1)


def run_layout(w,report):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from . import projects
    from .experiment import atomic_json
    report=Path(report).resolve();shots=[]
    try:
        if not w.active_project:raise ValueError("缩放验收需要一个已保存项目")
        project=projects.read(w.active_project)
        frequency=next(e for e in reversed(project["entries"]) if e["schema"]=="frequency-1.0")
        w.resize(1180,820);w.open_result(w.active_project/frequency["folder"]);QTest.qWait(150)
        for mode in ("bode","poles","sensitivity","channels"):
            page=w.frequency_page;page.mode.setCurrentIndex(page.mode.findData(mode));QTest.qWait(60)
            image=report.with_name(report.stem+"-"+mode+".png");assert w.grab().save(str(image));shots.append(str(image))
        page.drawer.toggle.setFocus();QTest.keyClick(page.drawer.toggle,Qt.Key.Key_Space);QTest.qWait(60)
        assert page.drawer.scroll.isVisible()
        QTest.keyClick(page.drawer.toggle,Qt.Key.Key_Space)
        w.switch_page(7);QTest.qWait(100);image=report.with_name(report.stem+"-project.png");assert w.grab().save(str(image));shots.append(str(image))
        atomic_json(report,dict(passed=True,dpr=w.devicePixelRatioF(),frozen=bool(getattr(sys,"frozen",False)),screenshots=shots,window=[w.width(),w.height()]))
        w.close();QApplication.instance().exit(0)
    except BaseException as exc:
        atomic_json(report,dict(passed=False,error=str(exc),screenshots=shots))
        w.close();QApplication.instance().exit(1)
