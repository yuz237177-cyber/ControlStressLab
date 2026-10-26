"""Independent finite-grid/CSV audit; stdlib only, no product imports."""
import argparse
from copy import deepcopy
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import random


def read(path): return json.loads(path.read_text(encoding="utf8"))
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(folder):
    folder = Path(folder).resolve()
    manifest, config, status = (read(folder/name) for name in ("manifest.json","config.json","status.json"))
    assert manifest["schema_version"] == "robustness-1.0"
    assert status["artifacts_complete"] and manifest["artifacts_complete"]
    assert manifest["config"] == config and manifest["config_sha256"] == digest(folder/"config.json")
    for name,expected in read(folder/"checksums.json").items():
        p = (folder/name).resolve()
        assert p.is_relative_to(folder) and p.is_file() and digest(p) == expected,name
    axes, base = config["axes"],config["base"]
    ny = len(axes[1]["values"]) if len(axes) == 2 else 1
    expected = {(x,y,seed,name) for x,y,seed,name in itertools.product(range(len(axes[0]["values"])),range(ny),config["seeds"],base["selected_controllers"])}
    actual,records,pairing,errors = set(),[],{},[]
    params = {d["name"]:d["parameters"] for d in base["controllers"]}
    metrics_keys = ("rmse","iae","input_total_variation","saturation_fraction")
    for file in sorted((folder/"runs").glob("*.json")):
        r = read(file);records.append(r)
        x,y = r["axis_indices"]
        identity = (x,y,r["seed"],r["controller_name"])
        assert identity not in actual
        actual.add(identity)
        c = deepcopy(base)
        for axis,index in zip(axes,(x,y)):
            group,key = axis["key"].split(".")
            c[group][key] = axis["values"][index]
        c["conditions"]["seed"] = r["seed"]
        assert c == r["run_config"]
        assert {k:v for k,v in r["controller"].items() if k not in ("type","params_recorded")} == params[r["controller_name"]]
        assert {k:v for k,v in r["plant"].items() if k not in ("type","params_recorded")} == c["plant"]
        assert digest(folder/r["trace_file"]) == r["trace_file_sha256"]
        assert digest(folder/r["input_file"]) == r["input_sha256"]
        paired = read(folder/r["input_file"])
        assert paired["scenario"] == r["scenario"]
        pairing.setdefault((x,y,r["seed"]),set()).add(r["input_sha256"])
        s,m = r["scenario"],r["metrics"]
        rng = random.Random(r["seed"])
        for v in paired["noise"]:
            assert math.isclose(v,rng.gauss(0,s["noise_std"]),rel_tol=1e-12,abs_tol=1e-15)
        with (folder/r["trace_file"]).open(encoding="utf8",newline="") as stream:
            rows = [{k:float(v) if k not in ("action_taken","transition_completed") and v else v for k,v in row.items()} for row in csv.DictReader(stream)]
        if m["status"] != "completed":
            assert r["requirement"] == "run_failed"
            assert all(m[k] is None for k in metrics_keys)
            continue
        assert len(rows) == round(s["duration_s"]/s["dt_s"])+1
        assert rows[-1]["applied_input"] == "" and rows[-1]["interval_s"] == 0
        evaluated = [v for v in rows if v["time_s"] >= s["evaluation_start_s"]-1e-12 and v["interval_s"] > 0]
        duration = sum(v["interval_s"] for v in evaluated)
        iae = sum(abs(v["reference"]-v["output"])*v["interval_s"] for v in evaluated)
        rmse = math.sqrt(sum((v["reference"]-v["output"])**2*v["interval_s"] for v in evaluated)/duration)
        variation = sum(abs(b["applied_input"]-a["applied_input"]) for a,b in zip(evaluated,evaluated[1:]))
        saturation = sum(v["interval_s"] for v in evaluated if abs(v["requested_input"]-v["applied_input"]) > 1e-10)/duration
        values = dict(iae=iae,rmse=rmse,input_total_variation=variation,saturation_fraction=saturation,
            normalized_iae=iae/(r["reference_scale"]*(s["duration_s"]-s["evaluation_start_s"])),
            normalized_rmse=rmse/r["reference_scale"],input_variation_rate=variation/(r["input_limit"]*(s["duration_s"]-s["evaluation_start_s"])))
        for key,value in values.items():
            error = abs(value-m[key]);errors.append(error)
            assert error <= 1e-10+1e-10*abs(value),(r["case_id"],key,error)
        required = {"rmse_max":"rmse","saturation_fraction_max":"saturation_fraction","input_variation_rate_max":"input_variation_rate"}
        met = all(m[required[k]] <= threshold for k,threshold in config["thresholds"].items() if threshold is not None)
        assert r["requirement"] == ("met" if met else "not_met")
    assert actual == expected
    assert len(records) == status["expected_runs"] == status["written_runs"]
    assert all(len(hashes) == 1 for hashes in pairing.values())
    with (folder/"plan.csv").open(encoding="utf8",newline="") as stream:plan=list(csv.DictReader(stream))
    assert len(plan) == len(records) and {r["case_id"] for r in plan} == {r["case_id"] for r in records}
    result_records = {r["case_id"]:r for r in read(folder/"results.json")}
    assert result_records == {r["case_id"]:r for r in records}
    summary = read(folder/"summary.json")
    for cell in summary["cells"]:
        group = [r for r in records if r["controller_name"] == cell["controller_name"] and r["axis_indices"] == cell["axis_indices"]]
        failed = any(r["metrics"]["status"] != "completed" for r in group)
        classification = "run_failed" if failed else "not_met" if any(r["requirement"] == "not_met" for r in group) else "met"
        assert cell["requirement"] == classification
        for key in metrics_keys:
            expected_value = None if failed else max(r["metrics"][key] for r in group)
            assert cell["worst_observed"][key] == expected_value
    for name in base["selected_controllers"]:
        group = [r for r in records if r["controller_name"] == name and r["metrics"]["status"] == "completed"]
        selected = summary["worst_completed_rmse_case"][name]
        if not group: assert selected is None
        else:
            item = next(r for r in group if r["case_id"] == selected)
            assert item["metrics"]["rmse"] == max(r["metrics"]["rmse"] for r in group)
    return dict(passed=True,raw_traces_checked=len(records),paired_inputs_checked=len(pairing),failed_runs=status["failed_runs"],
        max_metric_abs_error=max(errors,default=0),audit_script_sha256=digest(Path(__file__)),
        scope="finite-grid coverage, frozen parameters, paired randomness, CSV metrics, thresholds and seed aggregation; no hardware or continuous-domain proof")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();result=audit(args.suite)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf8",newline="\n") as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))
