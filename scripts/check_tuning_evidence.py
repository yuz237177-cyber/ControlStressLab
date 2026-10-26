"""Independent tuning audit: stdlib only; never imports product modules."""
import argparse
from collections import defaultdict
import csv
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import itertools
import math
from pathlib import Path
import random


def read(p): return json.loads(p.read_text(encoding="utf8"))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def identity(value):
    def normalize(v):
        if type(v) in (int,float): return float(v)
        if isinstance(v,dict): return {k:normalize(x) for k,x in v.items()}
        if isinstance(v,list): return [normalize(x) for x in v]
        return v
    return hashlib.sha256(json.dumps(normalize(value),sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def input_plant(value):
    if value["model"]!="transfer_function":return value["plant"]
    p=value["plant"];den=[v/p["denominator"][0] for v in p["denominator"]]
    n=len(den)-1;tau=p["time_scale"]
    a=[[(-den[i+1] if j==0 else 1. if j==i+1 else 0.)/tau for j in range(n)] for i in range(n)]
    def numerator(v,scale):
        while len(v)>1 and v[0]==0:v=v[1:]
        return [x/p["denominator"][0]*scale/tau for x in [0.]*(n-len(v))+v]
    u=numerator(p["numerator"],p["gain_scale"]);d=numerator(p["disturbance_numerator"] or [0.],1.)
    return dict(A=a,B=list(map(list,zip(u,d))),C=[[1.]+[0.]*(n-1)],D=[[0.,0.]],initial_state=p["initial_state"])


def check_pid(rows,record,payload):
    """Recompute measurement availability, clipped actions and conditional integration."""
    p={k:v for k,v in record["controller"].items() if k not in ("type","params_recorded")}
    dt=payload["dt_s"];delay=round(payload["measurement_delay_s"]/dt)
    integral=derivative=0.;previous=None
    alpha=math.exp(-dt/p["derivative_filter_s"]) if p["derivative_filter_s"] else 0.
    for index,row in enumerate(rows):
        if row["output"]=="":continue
        available=rows[index-delay]["output"]+payload["noise"][index-delay] if index>=delay else (payload["plant"]["initial_state"][0] if payload["model"]=="transfer_function" else payload["plant"]["initial_output"])
        assert math.isclose(row["measurement"],available,rel_tol=1e-10,abs_tol=1e-11)
        assert row["reference"]==payload["reference"][index] and row["disturbance"]==payload["disturbance"][index]
        if row["applied_input"]=="":continue
        error=row["reference"]-available
        raw=0. if previous is None else (available-previous)/dt
        derivative=alpha*derivative+(1-alpha)*raw
        pending=integral+p["ki"]*error*dt
        requested=p["kp"]*(p.get("beta",1.)*row["reference"]-available)+pending-p["kd"]*derivative
        applied=max(-payload["input_limit"],min(payload["input_limit"],requested))
        assert math.isclose(row["requested_input"],requested,rel_tol=1e-9,abs_tol=1e-10),(record["case_id"],index,"PID request")
        assert math.isclose(row["applied_input"],applied,rel_tol=1e-9,abs_tol=1e-10)
        if not (p["anti_windup"] and error*(requested-applied)>0):integral=pending
        previous=available


def audit(folder):
    folder=Path(folder).resolve()
    def path(name):
        p=(folder/name).resolve()
        assert p.is_relative_to(folder) and p.is_file(),name
        return p
    config,manifest,status,plan,summary=(read(path(n)) for n in ("config.json","manifest.json","status.json","plan.json","summary.json"))
    schema=manifest["schema_version"]
    assert schema in ("tuning-search-1.0","tuning-validation-1.0")
    assert status["artifacts_complete"] and manifest["artifacts_complete"] and manifest["execution_complete"]
    assert manifest["config"]==config==plan["config"]
    checksums=read(path("checksums.json"))
    assert {"config.json","manifest.json","status.json","plan.json","summary.json"}<=checksums.keys()
    for name,expected in checksums.items():assert sha(path(name))==expected,name
    assert {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}-{"checksums.json"}<=checksums.keys()
    records=[read(p) for p in sorted((folder/"runs").glob("*.json"))]
    assert len(records)==manifest["expected_runs"]==status["written_runs"]
    stage="search" if schema=="tuning-search-1.0" else "validation"
    cases={c["case_id"]:c for c in plan[stage]}
    # Expand the declared protocol independently, rather than trusting a saved plan
    # that could have silently omitted a difficult condition.
    axis_keys=[a["key"] for a in config["search"]["axes"]]
    declared_points=[dict(zip(axis_keys,p)) for p in itertools.product(*(a["values"] for a in config["search"]["axes"]))] if stage=="search" else config["validation"]["points"]
    expected_cases={}
    for fi,family in enumerate(config[stage]["families"]):
        for pi,point in enumerate(declared_points):
            for si,seed in enumerate(config[stage]["seeds"]):
                name=f"{stage}_f{fi}_p{pi}_s{si}"
                expected_cases[name]=(family,pi,si,seed,point)
    assert cases.keys()==expected_cases.keys()
    for name,case in cases.items():
        family,pi,si,seed,point=expected_cases[name]
        v=deepcopy(config["base"]);v["reference"],v["disturbance"]=deepcopy(family["reference"]),deepcopy(family["disturbance"])
        v["conditions"].update(family["conditions"],seed=seed)
        if stage=="validation":v["disturbance"]["seed"]=config[stage]["waveform_seeds"][si]
        for key,level in point.items():
            group,field=key.split(".");v[group][field]=level
        assert case["run_config"]==v
        assert (case["family"],case["condition_index"],case["input_index"],case["seed"],case["point"])==(family["id"],pi,si,seed,point)
    proposed={c["candidate_id"]:c["parameters"] for c in plan["candidates"]}
    original=next(d["parameters"] for d in config["base"]["controllers"] if d["name"]==config["controller"])
    generated={};seen=set()
    for index in range(config["candidate_budget"]):
        p=deepcopy(original)
        if index:
            for key,r in config["ranges"].items():
                bits=int.from_bytes(hashlib.sha256(f"{config['search_seed']}|{index}|{key}".encode()).digest()[:8],"big")>>11
                u=bits/9007199254740992
                a,b=r["low"],r["high"]
                p[key]=a if a==b else a+(b-a)*u if r["scale"]=="linear" else math.exp(math.log(a)+(math.log(b)-math.log(a))*u)
        fingerprint=identity(p)
        if fingerprint not in seen:generated[index]=p;seen.add(fingerprint)
    assert generated.keys()==proposed.keys()
    for cid,p in generated.items():
        for k,v in p.items():
            if type(v)in (int,float):assert math.isclose(v,proposed[cid][k],rel_tol=1e-14,abs_tol=0),(cid,k)
            else:assert v==proposed[cid][k]
    if stage=="search":ids=set(proposed)
    else:
        selection=read(path("selection.json"));ids={0,*selection["candidate_ids"]}
        assert selection["main_candidate_id"] in selection["candidate_ids"]
        assert sha(path("evidence/selection/selection.json"))==manifest["selection_sha256"]
        assert selection==read(path("evidence/selection/selection.json"))
        assert sha(path("evidence/search/manifest.json"))==selection["search_manifest_sha256"]
        assert sha(path("evidence/search/checksums.json"))==selection["search_checksums_sha256"]
        assert manifest["observation"] in ("first_use_in_workspace","reproduction_same_frozen_selection")
        if "validation_started_utc" in manifest:
            assert datetime.fromisoformat(selection["frozen_utc"])<=datetime.fromisoformat(manifest["validation_started_utc"])
    expected={(cid,name) for cid in ids for name in cases}
    actual=set();grouped=defaultdict(list);pairs=defaultdict(set);largest=0.
    thresholds={"error_max":"normalized_rmse","saturation_max":"saturation_fraction","variation_max":"input_variation_rate"}
    for r in records:
        cid=r["candidate_id"]
        case_name=r["case_id"].split("_",1)[1]
        key=(cid,case_name);assert key in expected and key not in actual;actual.add(key)
        case=cases[case_name];s=r["scenario"];m=r["metrics"]
        assert r["family"]==case["family"] and r["condition_index"]==case["condition_index"] and r["input_index"]==case["input_index"]
        assert {k:v for k,v in r["controller"].items() if k not in ("type","params_recorded")}==proposed[cid]
        assert {k:v for k,v in r["plant"].items() if k not in ("type","params_recorded")}==case["run_config"]["plant"]
        assert sha(path(r["trace_file"]))==r["trace_file_sha256"]
        assert sha(path(r["input_file"]))==r["input_sha256"]
        inp=read(path(r["input_file"]));payload=inp["payload"]
        assert inp["scenario"]==s and inp["noise"]==payload["noise"]
        assert identity(payload)==case["input_sha256"]==r["stimulus_sha256"]
        assert payload["plant"]==input_plant(case["run_config"]) and payload["measurement_delay_s"]==s["measurement_delay_s"]
        assert payload["reference"]==s["reference"]["values"] and payload["disturbance"]==s["load"]["values"]
        rng=random.Random(r["seed"])
        assert inp["noise"]==[rng.gauss(0,s["noise_std"]) for _ in inp["noise"]]
        pairs[case_name].add(r["input_sha256"])
        with path(r["trace_file"]).open(encoding="utf8",newline="") as stream:
            rows=[{k:float(v) if v and k not in ("action_taken","transition_completed") else v for k,v in row.items()} for row in csv.DictReader(stream)]
        check_pid(rows,r,payload)
        if m["status"]!="completed":
            assert all(m[k] is None for k in ("rmse","iae","input_total_variation","normalized_rmse","saturation_fraction","input_variation_rate"))
            assert r["requirement"]=="run_failed"
            grouped[cid].append((r,None));continue
        assert len(rows)==round(s["duration_s"]/s["dt_s"])+1
        assert rows[-1]["interval_s"]==0 and rows[-1]["applied_input"]==""
        window=[v for v in rows if v["time_s"]>=s["evaluation_start_s"]-1e-12 and v["interval_s"]>0]
        duration=sum(v["interval_s"] for v in window)
        rmse=math.sqrt(sum((v["reference"]-v["output"])**2*v["interval_s"] for v in window)/duration)
        tv=sum(abs(b["applied_input"]-a["applied_input"]) for a,b in zip(window,window[1:]))
        sat=sum(v["interval_s"] for v in window if abs(v["requested_input"]-v["applied_input"])>1e-10)/duration
        values=dict(rmse=rmse,normalized_rmse=rmse/r["reference_scale"],input_total_variation=tv,saturation_fraction=sat,input_variation_rate=tv/(r["input_limit"]*(s["duration_s"]-s["evaluation_start_s"])))
        for k,v in values.items():
            assert math.isclose(m[k],v,rel_tol=1e-10,abs_tol=1e-11),(r["case_id"],k,m[k],v)
            largest=max(largest,abs(m[k]-v))
        issues=[dict(kind="not_met",metric=k,value=values[k],threshold=config["thresholds"][t]) for t,k in thresholds.items() if config["thresholds"][t] is not None and values[k]>config["thresholds"][t]]
        assert r["issues"]==issues and r["requirement"]==("not_met" if issues else "met")
        grouped[cid].append((r,values))
    assert actual==expected and all(len(p)==1 for p in pairs.values())
    if stage=="search":
        computed={}
        for cid,rows in grouped.items():
            feasible=all(v is not None and r["requirement"]=="met" for r,v in rows)
            saved=next(c for c in summary["candidates"] if c["candidate_id"]==cid)
            assert feasible==saved["feasible"]
            if not feasible:assert saved["J1"]is None and saved["J2"]is None;continue
            families=defaultdict(lambda:defaultdict(list))
            for r,v in rows:families[r["family"]][r["condition_index"]].append(v["normalized_rmse"])
            j1=sum(sum(max(v) for v in cells.values())/len(cells) for cells in families.values())/len(families)
            j2=max(v["input_variation_rate"] for _,v in rows)
            assert math.isclose(j1,saved["J1"],rel_tol=1e-10,abs_tol=1e-11)
            assert math.isclose(j2,saved["J2"],rel_tol=1e-10,abs_tol=1e-11)
            computed[cid]=(saved["J1"],saved["J2"])
        front=sorted(i for i,(x,y) in computed.items() if not any(a<=x and b<=y and (a<x or b<y) for a,b in computed.values()))
        assert front==sorted(summary["frontier_ids"])
    else:
        assert summary["main_candidate_id"]==selection["main_candidate_id"] and summary["validation_ranking_allowed"]is False
        for cid,rows in grouped.items():
            states={r["requirement"] for r,_ in rows}
            outcome="run_failed" if "run_failed" in states else "metric_invalid" if "metric_invalid" in states else "not_met" if states!={"met"} else "met"
            saved=next(c for c in summary["candidates"] if c["candidate_id"]==cid)
            assert saved["outcome"]==outcome
            if cid==summary["main_candidate_id"]:assert summary["main_outcome"]==outcome
        audit(folder/"evidence/search")
    return dict(passed=True,schema=schema,records=len(records),paired_conditions=len(pairs),max_metric_abs_difference=largest)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();result=audit(args.suite)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf8") as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(result))


if __name__=="__main__":main()
