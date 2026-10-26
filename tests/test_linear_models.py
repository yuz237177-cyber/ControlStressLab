"""Numerical contract checks for declared transfer functions and saved workflows."""
from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from controlstresslab.linear_models import TransferFunctionPlant,continuous,default_plant,sampled,snapshot,template,validate_plant
from controlstresslab.experiment import Cancelled,default_config,execute,export_zip,load_result,read_trace,validate_config

SCIENCE=importlib.util.find_spec("scipy") is not None and importlib.util.find_spec("numpy") is not None

class DefinitionChecks(unittest.TestCase):
    def test_invalid_models_rejected_without_silently_repairing(self):
        invalid=[("denominator",[0,1]),("denominator",[1]),("denominator",[1,1,1,1,1,1]),
            ("numerator",[1,1]),("initial_state",[0,0]),("numerator",[True]),("initial_state",[float("nan")]),
            ("disturbance_numerator",[]),("disturbance_numerator",[float("inf")]),("time_scale",0),
            ("time_scale",True),("gain_scale",float("inf")),("units",dict(input="u",output="y")),
            ("denominator",[1e-12,1]),("name","")]
        for key,v in invalid:
            with self.subTest(key=key,value=v):
                p=default_plant();p[key]=v
                with self.assertRaises(ValueError):validate_plant(p)
    def test_zero_negative_gains_integrators_and_unstable_models_are_legal(self):
        for den in ([1,0],[1,-1],[1,2,1],[1,0,0,0,0]):
            for gain in (-1,0,1):
                p=default_plant();p.update(denominator=den,gain_scale=gain,initial_state=[0.]*(len(den)-1))
                self.assertEqual(validate_plant(p),p)

@unittest.skipUnless(SCIENCE,"optional analysis dependencies are not installed")
class LinearNumericalChecks(unittest.TestCase):
    def test_first_order_matches_legacy_at_every_sample_with_distinct_input_channels(self):
        from controlstresslab.models import FirstOrder
        for gain in (-2,0,1.7):
            physical=dict(gain=gain,tau_s=1.3,initial_output=.37)
            old=FirstOrder(**physical);new=TransferFunctionPlant(**template("first_order",physical))
            for i in range(180):
                u=math.sin(i*.13);d=math.cos(i*.17)*.4;dt=(.01,.03)[i%2]
                old.advance(u,d,dt);new.advance(u,d,dt)
                self.assertAlmostEqual(old.output,new.output,places=12)
    def test_second_order_matches_physical_states_including_repeated_poles(self):
        from controlstresslab.extended_models import MassSpringDamper
        for damping in (0.,.7,4.,7.):
            physical=dict(mass_kg=1.,damping_N_s_m=damping,stiffness_N_m=4.,initial_output=.37,initial_velocity_m_s=-.42)
            old=MassSpringDamper(**physical);new=TransferFunctionPlant(**template("second_order",physical))
            for i in range(160):
                u=math.sin(i*.1);d=.3 if i%9 else -.2
                old.advance(u,d,.02);new.advance(u,d,.02)
                self.assertAlmostEqual(old.output,new.output,places=12)
    def test_integrator_exact_solution_no_inverse_of_singular_A(self):
        p=template("integrator");p.update(initial_state=[.2],gain_scale=-2.,time_scale=3.)
        plant=TransferFunctionPlant(**p)
        for i in range(100):plant.advance(.8,.3,.03)
        self.assertAlmostEqual(plant.output,.2+(-2*.8+.3)*3/3,places=12)
    def test_general_numerators_and_scaling_match_transfer_polynomials(self):
        import numpy as np
        p=template("fourth_order");p.update(numerator=[.7,-.2,.3],disturbance_numerator=[.5,.2],gain_scale=-1.7,time_scale=2.3)
        a,b,c,d=map(np.asarray,continuous(p))
        for w in (.01,.2,1.,10.,100.):
            response=c@np.linalg.solve(1j*w*np.eye(4)-a,b)+d
            z=1j*w*p["time_scale"];den=np.polyval(p["denominator"],z)
            self.assertAlmostEqual(abs(response[0,0]-p["gain_scale"]*np.polyval(p["numerator"],z)/den),0,places=12)
            self.assertAlmostEqual(abs(response[0,1]-np.polyval(p["disturbance_numerator"],z)/den),0,places=12)
    def test_high_order_replay_against_independently_constructed_DOP853(self):
        import numpy as np
        from scipy.signal import tf2ss
        from scipy.integrate import solve_ivp
        for key in ("integrator","fourth_order"):
            p=template(key)
            if key=="fourth_order":p.update(numerator=[.7,-.2,.3],disturbance_numerator=[.5,.2],initial_state=[.1,-.2,.3,-.1])
            p.update(gain_scale=-1.7,time_scale=2.3)
            au,bu,cu,du=tf2ss(p["numerator"],p["denominator"])
            _,_,cd,_=tf2ss(p["disturbance_numerator"],p["denominator"])
            a=au.T/p["time_scale"];b=np.column_stack((cu[0]*p["gain_scale"],cd[0]))/p["time_scale"]
            x=np.array(p["initial_state"]);plant=TransferFunctionPlant(**p)
            for i in range(60):
                inputs=np.array([math.sin(i*.2),math.cos(i*.3)*.2]);dt=.035
                solution=solve_ivp(lambda t,state:a@state+b@inputs,(0,dt),x,method="DOP853",rtol=1e-11,atol=1e-13)
                self.assertTrue(solution.success);x=solution.y[:,-1]
                plant.advance(*inputs,dt)
                self.assertLess(np.max(np.abs(np.asarray(plant.state)-x)),1e-10)
    def test_hidden_unstable_pole_is_not_cancelled_in_snapshot(self):
        p=template("second_order");p.update(numerator=[1.,-1.],denominator=[1.,0.,-1.],disturbance_numerator=None)
        frozen=snapshot(p,.01)
        self.assertEqual(len(frozen["continuous"]["A"]),2)
        self.assertTrue(any(z["real"]>.99 for z in frozen["poles"]))
        self.assertEqual(len(frozen["sampled"]["B"][0]),2)
    def test_external_definition_edits_cannot_change_an_already_created_plant(self):
        p=default_plant();plant=TransferFunctionPlant(**p);plant.advance(1,0,.01)
        p["denominator"][1]=9
        view=plant.definition;view["numerator"][0]=9
        recorded=plant.to_config();recorded["gain_scale"]=9
        plant.advance(1,0,.01)
        self.assertAlmostEqual(plant.output,1-math.exp(-.02),places=13)
        self.assertEqual(plant.to_config(),default_plant())

    def test_leading_zero_numerator_coefficients_preserve_equivalent_dynamics(self):
        p=default_plant();p.update(numerator=[0.,0.,2.],disturbance_numerator=[0.,1.])
        plant=TransferFunctionPlant(**p);plant.advance(1,.3,.02)
        self.assertAlmostEqual(plant.output,2.3*(1-math.exp(-.02)),places=13)
        self.assertEqual(snapshot(p,.02)["definition"],p)

    def test_no_disturbance_is_an_explicit_contract(self):
        p=default_plant();p["disturbance_numerator"]=None;plant=TransferFunctionPlant(**p)
        with self.assertRaisesRegex(ValueError,"扰动通道"):plant.advance(1,.1,.01)
        for dt in (True,0,-1,float("inf")):
            with self.assertRaises(ValueError):plant.advance(1,0,dt)
        c=default_config("transfer_function");c["plant"]=p
        with self.assertRaisesRegex(ValueError,"没有声明扰动通道"):validate_config(c)
        c["disturbance"].update(kind="constant",offset=0,amplitude=0)
        validate_config(c)

@unittest.skipUnless(SCIENCE,"optional analysis dependencies are not installed")
class LinearWorkflowChecks(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def config(self):
        c=default_config("transfer_function");c["selected_controllers"]=["PI","PID_aw","TwoDOF_PID"]
        c["conditions"].update(dt_s=.05,noise_std=.01,measurement_delay_s=.05)
        return c
    def test_full_experiment_snapshot_export_reopen_and_immutability(self):
        c=self.config();out=self.root/"中文实验";execute(out,c)
        loaded=load_result(out);self.assertEqual(loaded["verification"],"校验通过")
        before=(out/"model-snapshot.json").read_bytes();self.assertEqual(len(loaded["records"]),3)
        for r in loaded["records"]:
            self.assertEqual(r["metrics"]["status"],"completed")
            self.assertIsNone(read_trace(out,r)[-1]["applied_input"])
        c["plant"]["denominator"]=[1,2]
        self.assertEqual((out/"model-snapshot.json").read_bytes(),before)
        target=self.root/"transfer.zip";export_zip(out,target)
        moved=self.root/"moved";zipfile.ZipFile(target).extractall(moved)
        # Export layout includes the original experiment folder name.
        manifest=next(moved.rglob("manifest.json"))
        self.assertEqual(load_result(manifest.parent)["verification"],"校验通过")
    def test_scan_and_tuning_freeze_validate_keep_per_case_matrices(self):
        from controlstresslab import robustness,tuning,tuning_protocol,tuning_validation
        c=self.config();c["selected_controllers"]=["PI"]
        scan=robustness.default_config(c);scan["axes"]=[dict(key="plant.gain_scale",values=[.8,1.2])]
        robustness.execute(self.root/"scan",scan)
        self.assertEqual(len(list((self.root/"scan/models").glob("*.json"))),2)
        tc=tuning_protocol.default_config(c,"PI");tc["candidate_budget"]=2
        tc["search"]["axes"]=tc["search"]["axes"][:1];tc["search"]["families"]=tc["search"]["families"][:1]
        tc["search"]["seeds"]=[11];tc["thresholds"]=dict(error_max=None,saturation_max=1.,variation_max=None)
        axis=tc["search"]["axes"][0]["key"]
        tc["validation"]["points"]=[{axis:.95}];tc["validation"]["families"]=tc["validation"]["families"][:1]
        tc["validation"]["seeds"]=[22];tc["validation"]["waveform_seeds"]=[33]
        tuning.execute(self.root/"search",tc)
        for folder in ("scan","search"):
            result=load_result(self.root/folder);self.assertEqual(result["verification"],"校验通过")
            for record in result["records"]:
                path=self.root/folder/record["model_snapshot"]
                self.assertTrue(path.exists());self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["definition"],record["run_config"]["plant"])
        summary=json.loads((self.root/"search/summary.json").read_text(encoding="utf-8"))
        cid=next(v["candidate_id"] for v in summary["candidates"] if v["feasible"])
        tuning_validation.freeze(self.root/"selection",dict(search_folder=str(self.root/"search"),candidate_ids=[cid],main_candidate_id=cid))
        tuning_validation.execute(self.root/"validation",dict(selection_folder=str(self.root/"selection")))
        loaded=load_result(self.root/"validation")
        self.assertEqual(loaded["verification"],"校验通过");self.assertTrue(loaded["records"][0]["model_snapshot"])
    def test_no_disturbance_default_protocol_does_not_invent_channel(self):
        from controlstresslab.tuning_protocol import default_config as plan,prepare
        c=default_config("transfer_function");c["plant"]["disturbance_numerator"]=None
        c["disturbance"].update(kind="constant",offset=0,amplitude=0)
        prepared=prepare(plan(c))
        self.assertEqual({x["family"] for x in prepared["search"]},{"step","tracking"})
    def test_tuning_identity_uses_dynamics_instead_of_model_label_or_equivalent_coefficients(self):
        from controlstresslab.tuning_protocol import input_payload,digest,default_config as plan,prepare
        c=default_config("transfer_function");changed=deepcopy(c)
        changed["plant"]["name"]="改过的名称";changed["plant"]["units"]["output"]="标签修改"
        changed["plant"].update(numerator=[0.,2.],denominator=[2.,2.],disturbance_numerator=[2.])
        self.assertEqual(digest(input_payload(c)),digest(input_payload(changed)))
        tc=plan(c);signature=prepare(tc)["validation"][0]["input_sha256"]
        renamed=deepcopy(tc);renamed["base"]["plant"]["name"]="又改名";renamed["observed_inputs"]=[signature]
        with self.assertRaisesRegex(ValueError,"已观察"):prepare(renamed)

    def test_negative_and_zero_gain_default_plans_are_well_formed(self):
        from controlstresslab.tuning_protocol import default_config as plan,prepare
        for gain in (-1.,0.):
            c=default_config("transfer_function");c["plant"]["gain_scale"]=gain
            prepare(plan(c))
    def test_invalid_models_and_unsupported_controller_create_no_output(self):
        for field,value in (("numerator",[1,1]),("denominator",[0,1])):
            c=self.config();c["plant"][field]=value;out=self.root/field
            with self.assertRaises(ValueError):execute(out,c)
            self.assertFalse(out.exists())
        c=self.config();c["selected_controllers"]=["LADRC"]
        with self.assertRaisesRegex(ValueError,"兼容性"):execute(self.root/"adrc",c)
        self.assertFalse((self.root/"adrc").exists())
    def test_wrong_control_direction_retains_failed_run_instead_of_rejecting_model(self):
        c=self.config();c["plant"]["gain_scale"]=-1.;c["conditions"]["output_bound"]=2.
        _,failed=execute(self.root/"negative-gain",c)
        self.assertGreater(failed,0)
        loaded=load_result(self.root/"negative-gain")
        self.assertEqual(loaded["verification"],"校验通过")
        self.assertEqual(loaded["status"]["state"],"completed_with_failures")
        self.assertTrue(any(r["metrics"]["status"]!="completed" for r in loaded["records"]))

    def test_open_loop_completed_cancelled_and_unstable_failure_are_distinct(self):
        from controlstresslab import model_analysis
        c=dict(plant=template("integrator"),dt_s=.05,duration_s=2.)
        model_analysis.execute(self.root/"preview",c,plots=False)
        loaded=load_result(self.root/"preview");self.assertEqual(loaded["verification"],"校验通过")
        self.assertEqual(loaded["status"]["state"],"completed")
        with self.assertRaises(Cancelled):model_analysis.execute(self.root/"cancel",c,plots=False,should_cancel=lambda:True)
        self.assertFalse(load_result(self.root/"cancel")["status"]["artifacts_complete"])
        c["plant"]=default_plant();c["plant"]["denominator"]=[1,-20]
        with self.assertRaisesRegex(ValueError,"观察范围"):model_analysis.execute(self.root/"unstable",c,plots=False)
        self.assertNotEqual(load_result(self.root/"unstable")["status"]["state"],"completed")

if __name__=="__main__":unittest.main()

