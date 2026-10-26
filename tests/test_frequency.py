"""Frequency mathematics, actual PID timing, finite-band states and frozen sources."""
from copy import deepcopy
import importlib.util,json
from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
AVAILABLE=importlib.util.find_spec("scipy") is not None
if AVAILABLE:
    import numpy as np
    from controlstresslab.frequency import default_config,validate_config,calculate,execute
    from controlstresslab.frequency_model import compile_model,response,pole_summary
    from controlstresslab.frequency_validation import consistency
from controlstresslab.experiment import default_config as base_config,Cancelled,load_result,sha
@unittest.skipUnless(AVAILABLE,"analysis optional dependencies")
class FrequencyChecks(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_actual_pid_timing_for_all_models_delays_and_zero_terms(self):
        for model in ("first_order","second_order","transfer_function"):
            for name,delay,ki,kd,tau in (("PI",0,1.,0.,.03),("PID_aw",.07,0.,.2,0.),("TwoDOF_PID",.01,.8,.2,.03)):
                base=base_config(model);base["selected_controllers"]=[name];base["conditions"]["measurement_delay_s"]=delay
                params=next(d["parameters"] for d in base["controllers"] if d["name"]==name);params.update(ki=ki,kd=kd,derivative_filter_s=tau)
                folder=self.root/(model+name);folder.mkdir()
                result,_=consistency(base,compile_model(base,name),folder)
                self.assertEqual(result["state"],"passed",(model,name,result))
                self.assertTrue(result["terminal_action_absent"])
    def test_closed_matrix_matches_all_algebraic_channels(self):
        base=base_config("second_order");base["conditions"]["measurement_delay_s"]=.07
        m=compile_model(base,"PID_aw");v=response(m,[.1,1.,10.])
        a,b,c,d=(np.array(m["closed"][key]) for key in ("A","B","C","D"))
        for i,w in enumerate((.1,1.,10.)):
            closed=c@np.linalg.solve(np.exp(1j*w*m["dt_s"])*np.eye(len(a))-a,b)+d
            for actual,key in ((closed[0,0],"Y_R"),(closed[0,1],"Y_D"),(closed[0,2],"Y_N"),(closed[1,2],"U_N")):
                self.assertLess(abs(actual-v[key][i]),1e-9)
    def test_two_dof_weight_changes_reference_but_not_internal_poles(self):
        base=base_config();a=compile_model(base,"TwoDOF_PID")
        next(d["parameters"] for d in base["controllers"] if d["name"]=="TwoDOF_PID")["beta"]=0.
        b=compile_model(base,"TwoDOF_PID")
        np.testing.assert_array_equal(a["closed"]["A"],b["closed"]["A"])
        np.testing.assert_allclose(response(a,[1])["L"],response(b,[1])["L"])
        self.assertGreater(abs(response(a,[1])["Y_R"][0]-response(b,[1])["Y_R"][0]),.01)
    def test_delay_is_measurement_phase_with_no_extra_sample(self):
        base=base_config();a=compile_model(base,"PID_aw");base["conditions"]["measurement_delay_s"]=.07;b=compile_model(base,"PID_aw")
        omega=np.array([.2,1.,5.]);ratio=response(b,omega)["L"]/response(a,omega)["L"]
        np.testing.assert_allclose(ratio,np.exp(-1j*omega*.07),atol=1e-12)
    def test_hidden_unstable_modes_are_not_cancelled(self):
        base=base_config("transfer_function");base["plant"].update(denominator=[1.,-1.],numerator=[0.])
        model=compile_model(base,"PI");self.assertEqual(pole_summary(model)["state"],"unstable")
        summary,rows=calculate(model,default_config(base))
        self.assertIsNone(summary["margins"]["gm"]["value"]);self.assertEqual(rows[0]["L_status"],"zero_channel")
        self.assertIsNone(rows[0]["L_db"])
    def test_margin_crossovers_match_independent_control_frd(self):
        if importlib.util.find_spec("control") is None:self.skipTest("reference-only control not installed")
        import control
        c=default_config();m=compile_model(c["base"],"PID_aw");summary,rows=calculate(m,c)
        w=np.array([r["omega_rad_s"] for r in rows]);loop=response(m,w)["L"]
        gm,pm,_,wpc,wgc,_=control.stability_margins((abs(loop),np.unwrap(np.angle(loop))*180/np.pi,w),returnall=True)
        for points,kind in ((wpc,"phase"),(wgc,"gain")):
            actual=[e["omega_rad_s"] for e in summary["crossovers"] if e["kind"]==kind]
            for wanted in points:self.assertTrue(any(abs(v/wanted-1)<1e-4 for v in actual),(actual,points))
    def test_illegal_bands_delay_and_ladrc_rejected_before_output(self):
        for key,value in (("omega_min",0),("omega_max",400),("points",2),("max_points",500)):
            c=default_config();c[key]=value;out=self.root/key
            with self.assertRaises(ValueError):execute(out,c)
            self.assertFalse(out.exists())
        c=default_config();c["base"]["selected_controllers"]=["LADRC"]
        with self.assertRaises(ValueError):validate_config(c)
        c=default_config();c["base"]["conditions"]["measurement_delay_s"]=1.29
        with self.assertRaisesRegex(ValueError,"128"):validate_config(c)
    def test_saved_analysis_has_complete_plots_and_checks(self):
        out=self.root/"频域";execute(out,default_config(),plots=True)
        self.assertEqual(load_result(out)["verification"],"校验通过")
        self.assertEqual(len(list((out/"figures").glob("*"))),8)
        summary=json.loads((out/"summary.json").read_text(encoding="utf-8"))
        self.assertTrue(all(r["time_check"]["state"]=="passed" and r["sine_check"]["state"]=="passed" for r in summary))
    def test_cancel_never_marks_complete(self):
        out=self.root/"cancel"
        with self.assertRaises(Cancelled):execute(out,default_config(),should_cancel=lambda:True)
        self.assertFalse(load_result(out)["status"]["artifacts_complete"])
    def test_moved_frequency_result_can_recompute_after_original_source_is_gone(self):
        from controlstresslab.experiment import execute as experiment
        from controlstresslab.projects import rebase_frequency
        base=base_config();base["selected_controllers"]=["PID_aw"]
        source=self.root/"origin";experiment(source,base)
        c=default_config(base);c["source"]=dict(folder=str(source),case_id="PID_aw",manifest_sha256=sha(source/"manifest.json"),producer_version=load_result(source)["manifest"]["package_version"])
        analysis=self.root/"analysis";execute(analysis,c)
        original=(analysis/"config.json").read_bytes()
        assert source.resolve().parent==self.root.resolve() and analysis.resolve().parent==self.root.resolve()
        source.rename(self.root/"unavailable");moved=self.root/"moved";analysis.rename(moved)
        self.assertEqual(load_result(moved)["verification"],"校验通过")
        draft=rebase_frequency(moved,json.loads(original))
        self.assertNotEqual(draft["source"]["folder"],str(source))
        execute(self.root/"recomputed",draft)
        self.assertEqual((moved/"config.json").read_bytes(),original)
        self.assertEqual(load_result(self.root/"recomputed")["verification"],"校验通过")

    def test_frozen_source_cannot_be_relabelled_after_editing(self):
        from controlstresslab.experiment import execute as experiment
        folder=self.root/"source";base=base_config();experiment(folder,base)
        c=default_config(base);c["source"]=dict(folder=str(folder),case_id="PI",manifest_sha256=sha(folder/"manifest.json"),producer_version=load_result(folder)["manifest"]["package_version"])
        validate_config(c);c["base"]["plant"]["gain"]=2.
        with self.assertRaisesRegex(ValueError,"不一致"):validate_config(c)
if __name__=="__main__":unittest.main()
