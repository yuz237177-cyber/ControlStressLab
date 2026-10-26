"""Finite tuning contracts, independent validation, negative controls and archives."""
from copy import deepcopy
import hashlib
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from controlstresslab.experiment import Cancelled, atomic_json, export_zip, load_result, read_trace
from controlstresslab.tuning import execute
from controlstresslab.tuning_objectives import assess, summarize
from controlstresslab.tuning_protocol import default_config, digest, prepare
from controlstresslab.tuning_validation import freeze, execute as validate


def small(model="first_order",controller="PID_aw"):
    c=default_config(controller=controller) if model=="first_order" else default_config(__import__("controlstresslab.experiment",fromlist=["default_config"]).default_config(model),controller)
    c["base"]["conditions"]["noise_std"]=.01
    c["candidate_budget"]=4
    c["thresholds"]["saturation_max"]=1
    c["search"]["axes"]=c["search"]["axes"][:1]
    c["search"]["families"]=c["search"]["families"][:1]
    c["search"]["seeds"]=[11]
    c["validation"]["points"]=[{c["search"]["axes"][0]["key"]:.95}]
    c["validation"]["families"]=c["validation"]["families"][:1]
    c["validation"]["seeds"]=[22];c["validation"]["waveform_seeds"]=[33]
    return c


def auditor():
    spec=importlib.util.spec_from_file_location("independent_tuning",ROOT/"scripts/check_tuning_evidence.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.audit


class TuningChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def search(self,c=None):
        execute(self.root/"search",small() if c is None else c)
        return self.root/"search"
    def frozen(self,folder=None,cids=None,main=0,target="selection"):
        folder=self.search() if folder is None else folder
        freeze(self.root/target,dict(search_folder=str(folder),candidate_ids=[0] if cids is None else cids,main_candidate_id=main))
        return self.root/target

    def test_default_budget_and_complete_predeclared_crossing(self):
        p=prepare(default_config())
        self.assertEqual(p["budget"]["search_runs"],768)
        self.assertEqual(p["budget"]["total_upper"],858)
        self.assertEqual(p["budget"]["intervals_upper"],1029600)
        self.assertEqual(len({c["input_sha256"] for c in p["search"]+p["validation"]}),54)
        self.assertEqual(p,prepare(default_config()))

    def test_strict_configuration_rejects_before_creating_output(self):
        changes=[("candidate_budget",True),("candidate_budget",1),("max_runs",2),("controller","LADRC"),("search_seed",-1),("observed_inputs",["not-a-hash"]),("extra",1)]
        for k,v in changes:
            c=small();c[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):execute(self.root/"invalid",c)
            self.assertFalse((self.root/"invalid").exists())
        c=small();c["thresholds"]={k:None for k in c["thresholds"]}
        with self.assertRaises(ValueError):prepare(c)
        c=small();c["ranges"]["kp"]["low"]=0
        with self.assertRaises(ValueError):prepare(c)
        c=small();c["validation"]["points"]=[{"conditions.measurement_delay_s":.015}]
        with self.assertRaises(ValueError):prepare(c)

    def test_baseline_outside_ranges_unchanged_and_candidate_aliases(self):
        c=small()
        c["ranges"]={"kp":dict(low=0.,high=0.,scale="linear")}
        p=prepare(c)
        self.assertEqual(len(p["candidates"]),2)
        self.assertEqual(len(p["aliases"]),2)
        self.assertGreater(p["candidates"][0]["parameters"]["kp"],0)
        self.assertEqual(p["candidates"][1]["parameters"]["kp"],0)
        self.assertTrue(p["warnings"])

    def test_duplicate_inputs_detect_renaming_zero_noise_and_split_reuse(self):
        c=small();c["base"]["conditions"]["noise_std"]=0;c["search"]["seeds"]=[11,12]
        with self.assertRaisesRegex(ValueError,"重复输入"):prepare(c)
        c=small();c["search"]["families"]*=2;c["search"]["families"][1]=deepcopy(c["search"]["families"][0]);c["search"]["families"][1]["id"]="renamed"
        with self.assertRaisesRegex(ValueError,"重复输入"):prepare(c)
        c=small();c["validation"]["families"]=deepcopy(c["search"]["families"]);c["validation"]["points"]=[{c["search"]["axes"][0]["key"]:.8}];c["validation"]["seeds"]=[11]
        with self.assertRaisesRegex(ValueError,"重复输入"):prepare(c)
        c=small();c["observed_inputs"]=[prepare(c)["validation"][0]["input_sha256"]]
        with self.assertRaisesRegex(ValueError,"已观察"):prepare(c)

    def test_units_do_not_change_stimulus_identity_and_numeric_spelling_matches(self):
        self.assertEqual(digest(dict(a=1)),digest(dict(a=1.)))
        self.assertNotEqual(digest(dict(a=True)),digest(dict(a=1)))

    def test_all_structures_and_two_models_preserve_pairing_and_terminal_semantics(self):
        for model in ("first_order","second_order"):
            for name in ("PI","PID_aw","TwoDOF_PID"):
                output=self.root/(model+name);c=small(model,name);execute(output,c)
                loaded=load_result(output)
                self.assertEqual(loaded["verification"],"校验通过")
                self.assertEqual(len(loaded["records"]),8)
                by_case={}
                for r in loaded["records"]:
                    by_case.setdefault((r["family"],r["condition_index"],r["input_index"]),set()).add(r["input_sha256"])
                    rows=read_trace(output,r);self.assertIsNone(rows[-1]["applied_input"])
                self.assertTrue(all(len(v)==1 for v in by_case.values()))
                self.assertTrue(auditor()(output)["passed"])

    def test_family_weights_worst_seed_and_nondominated_ties(self):
        def r(cid,f,c,s,e,v):return dict(case_id=f"{cid}{f}{c}{s}",candidate_id=cid,family=f,condition_index=c,input_index=s,metrics=dict(status="completed",normalized_rmse=e,input_variation_rate=v,saturation_fraction=0))
        records=[r(0,"a",0,0,1,2),r(0,"a",0,1,3,2),r(0,"b",0,0,5,2),r(0,"b",1,0,7,2)]
        config=dict(thresholds=dict(error_max=None,saturation_max=1,variation_max=None))
        result=assess(records,config["thresholds"],4)
        self.assertEqual(result["J1"],4.5);self.assertEqual(result["J2"],2)
        candidates=[dict(candidate_id=i) for i in range(4)]
        rows=[r(0,"a",0,0,1,3),r(1,"a",0,0,2,2),r(2,"a",0,0,3,3),r(3,"a",0,0,1,3)]
        self.assertEqual(summarize(candidates,rows,config,1)["frontier_ids"],[0,1,3])
        rows[0]["metrics"]["normalized_rmse"]=None
        self.assertFalse(summarize(candidates,rows,config,1)["candidates"][0]["feasible"])
        rows[0]["subset"]="validation"
        with self.assertRaisesRegex(ValueError,"禁止验证"):summarize(candidates,rows,config,1)

    def test_failure_and_constraint_breach_excluded_without_fallback(self):
        c=small();c["base"]["conditions"]["output_bound"]=.001
        folder=self.search(c);summary=json.loads((folder/"summary.json").read_text(encoding="utf8"))
        self.assertEqual(summary["feasible_count"],0)
        self.assertTrue(all(x["J1"] is None for x in summary["candidates"]))
        self.assertTrue(auditor()(folder)["passed"])
        with self.assertRaisesRegex(ValueError,"可行候选"):self.frozen(folder)
        self.assertFalse((self.root/"selection").exists())
        m=dict(status="completed",normalized_rmse=.2,saturation_fraction=.1,input_variation_rate=1)
        t=dict(error_max=.2,saturation_max=.1,variation_max=1)
        self.assertTrue(assess([dict(case_id="x",family="a",condition_index=0,metrics=m)],t,1)["feasible"])
        m["input_variation_rate"]=1.000001
        self.assertFalse(assess([dict(case_id="x",family="a",condition_index=0,metrics=m)],t,1)["feasible"])

    def test_frozen_validation_is_complete_independent_snapshot_and_not_reranked(self):
        source=self.search();selection=self.frozen(source,[0,1],1)
        before=(selection/"selection.json").read_bytes()
        validate(self.root/"validation",dict(selection_folder=str(selection)))
        result=load_result(self.root/"validation")
        self.assertEqual(result["verification"],"校验通过")
        summary=json.loads((self.root/"validation/summary.json").read_text(encoding="utf8"))
        self.assertEqual(summary["main_candidate_id"],1)
        self.assertFalse(summary["validation_ranking_allowed"])
        self.assertEqual(before,(selection/"selection.json").read_bytes())
        self.assertTrue(auditor()(self.root/"validation")["passed"])
        shutil.rmtree(source);shutil.rmtree(selection)
        self.assertEqual(load_result(self.root/"validation")["verification"],"校验通过")
        export_zip(self.root/"validation",self.root/"report.zip")
        self.assertTrue((self.root/"report.zip").is_file())

    def test_changed_source_or_receipt_and_nested_destination_rejected(self):
        source=self.search();selection=self.frozen(source)
        with self.assertRaisesRegex(ValueError,"之外"):freeze(source/"nested-selection",dict(search_folder=str(source),candidate_ids=[0],main_candidate_id=0))
        self.assertFalse((source/"nested-selection").exists())
        with self.assertRaisesRegex(ValueError,"之外"):validate(source/"nested",dict(selection_folder=str(selection)))
        self.assertFalse((source/"nested").exists())
        with (selection/"selection.json").open("a",encoding="utf8") as f:f.write(" ")
        with self.assertRaisesRegex(ValueError,"校验"):validate(self.root/"invalid",dict(selection_folder=str(selection)))
        self.assertFalse((self.root/"invalid").exists())

    def test_same_frozen_replay_is_labelled_and_other_selection_cannot_reuse(self):
        source=self.search();selection=self.frozen(source)
        validate(self.root/"v1",dict(selection_folder=str(selection)))
        validate(self.root/"v2",dict(selection_folder=str(selection)))
        self.assertEqual(load_result(self.root/"v2")["manifest"]["observation"],"reproduction_same_frozen_selection")
        other=self.frozen(source,[1],1,"other")
        with self.assertRaisesRegex(ValueError,"另一份选择"):validate(self.root/"bad",dict(selection_folder=str(other)))
        self.assertFalse((self.root/"bad").exists())
        with self.assertRaisesRegex(ValueError,"已启用"):execute(self.root/"repeat-search",small())

    def test_cancel_keeps_complete_rows_without_claiming_complete_search(self):
        events=[]
        with self.assertRaises(Cancelled):execute(self.root/"cancel",small(),progress=events.append,should_cancel=lambda:any(e["written"]>=1 for e in events))
        loaded=load_result(self.root/"cancel")
        self.assertFalse(loaded["status"]["artifacts_complete"])
        self.assertGreater(len(loaded["records"]),0)
        with self.assertRaises(ValueError):export_zip(self.root/"cancel",self.root/"bad.zip")

    def test_plot_failure_does_not_mark_artifacts_complete_and_output_not_overwritten(self):
        with patch("controlstresslab.tuning_plots.build",side_effect=OSError("injected plot error")):
            with self.assertRaises(OSError):execute(self.root/"plotfail",small(),plots=True)
        self.assertFalse(load_result(self.root/"plotfail")["status"]["artifacts_complete"])
        folder=self.search();before=(folder/"config.json").read_bytes()
        with self.assertRaises(FileExistsError):execute(folder,small())
        self.assertEqual(before,(folder/"config.json").read_bytes())

    def test_independent_audit_catches_forged_metric_even_if_checksum_updated(self):
        source=self.search()
        file=next((source/"runs").glob("*.json"));r=json.loads(file.read_text(encoding="utf8"));r["metrics"]["normalized_rmse"]=0;atomic_json(file,r)
        checks=json.loads((source/"checksums.json").read_text(encoding="utf8"));checks[file.relative_to(source).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest();atomic_json(source/"checksums.json",checks)
        self.assertEqual(load_result(source)["verification"],"校验通过")
        with self.assertRaises(AssertionError):auditor()(source)

    def test_independent_audit_catches_omitted_condition_with_valid_checksum(self):
        source=self.search();plan_file=source/"plan.json"
        plan=json.loads(plan_file.read_text(encoding="utf8"));plan["search"].pop();atomic_json(plan_file,plan)
        checks=json.loads((source/"checksums.json").read_text(encoding="utf8"));checks["plan.json"]=hashlib.sha256(plan_file.read_bytes()).hexdigest();atomic_json(source/"checksums.json",checks)
        self.assertEqual(load_result(source)["verification"],"校验通过")
        with self.assertRaises(AssertionError):auditor()(source)

    def test_independent_pid_audit_catches_changed_request_with_same_applied_input(self):
        c=small();c["base"]["conditions"]["input_limit"]=.1
        source=self.search(c)
        record_file=next((source/"runs").glob("c0_*.json"));r=json.loads(record_file.read_text(encoding="utf8"))
        trace=source/r["trace_file"]
        with trace.open(encoding="utf8",newline="") as stream:rows=list(csv.DictReader(stream))
        row=next(row for row in rows if row["requested_input"] and float(row["requested_input"])>.2)
        row["requested_input"]=str(float(row["requested_input"])+1)
        with trace.open("w",encoding="utf8",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        r["trace_file_sha256"]=hashlib.sha256(trace.read_bytes()).hexdigest();atomic_json(record_file,r)
        results=json.loads((source/"results.json").read_text(encoding="utf8"))
        results=[r if old["case_id"]==r["case_id"] else old for old in results];atomic_json(source/"results.json",results)
        checks=json.loads((source/"checksums.json").read_text(encoding="utf8"))
        for file in (trace,record_file,source/"results.json"):checks[file.relative_to(source).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
        atomic_json(source/"checksums.json",checks)
        self.assertEqual(load_result(source)["verification"],"校验通过")
        with self.assertRaisesRegex(AssertionError,"PID request"):auditor()(source)


if __name__=="__main__":unittest.main()
