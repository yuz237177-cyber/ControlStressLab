"""Audit frozen selections and recompute saved CSV metrics without product imports."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def read(path): return json.loads(path.read_text(encoding="utf8"))
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(suite):
    manifest, config = read(suite / "manifest.json"), read(suite / "config.json")
    status, selection = read(suite / "status.json"), read(suite / "selections.json")
    assert status["artifacts_complete"] and manifest["artifacts_complete"]
    assert digest(suite / "config.json") == manifest["config_sha256"]
    for name, value in read(suite / "checksums.json").items():
        path = (suite / name).resolve()
        assert path.is_relative_to(suite.resolve()) and digest(path) == value, name
    events = [json.loads(line) for line in (suite / "events.jsonl").read_text(encoding="utf8").splitlines()]
    assert [e["event"] for e in events] == ["training_started", "selection_frozen", "heldout_started", "benchmark_completed"]
    sha = digest(suite / "selections.json")
    assert manifest["selection_sha256"] == events[1]["selection_sha256"] == events[2]["selection_sha256"] == sha
    training_runs = 0
    logs = {}
    for key, selected in selection.items():
        candidates = read(suite / f"training/{key}.json")
        logs[key] = candidates
        assert len(candidates) == selected["candidate_count"] == config["candidate_budget"]
        feasible = []
        for index, c in enumerate(candidates):
            assert c["candidate_index"] == index
            assert [r["scenario"] for r in c["training"]] == ["step", "ramp", "disturbance_step"]
            metrics = [r["metrics"] for r in c["training"]]
            valid = all(m["status"] == "completed" and all(m[k] is not None and math.isfinite(m[k]) for k in ("normalized_iae", "input_variation_rate", "saturation_fraction")) for m in metrics)
            objective = sum(m["normalized_iae"] for m in metrics)/3 if valid else None
            allowed = valid and max(m["input_variation_rate"] for m in metrics) <= config["max_training_variation_rate"] and max(m["saturation_fraction"] for m in metrics) <= config["max_training_saturation_fraction"]
            assert c["assessment"]["objective"] == objective and c["assessment"]["feasible"] == allowed
            if allowed: feasible.append((objective, index))
            training_runs += 3
        assert selected["candidate_index"] == min(feasible)[1]
        assert selected["parameters"] == candidates[selected["candidate_index"]]["parameters"]
        assert selected["baseline_parameters"] == candidates[0]["parameters"]
    expected_cases = {(model, name, phase, family, factor, seed)
        for model in config["models"] for name in config["controllers"] for phase in ("baseline", "tuned")
        for family in ("sine", "chirp", "binary_disturbance", "noise_delay") for factor in config["parameter_factors"]
        for seed in (config["heldout_seeds"] if family in ("binary_disturbance", "noise_delay") else [0])}
    actual_cases, input_pairing, metric_errors = set(), {}, []
    checked = 0
    for file in sorted((suite / "runs").glob("*.json")):
        record = read(file)
        name = record["model_name"]+"__"+record["controller_name"]
        selected = selection[name]
        expected_params = selected["parameters"] if record["phase"] == "tuned" else selected["baseline_parameters"]
        assert {k: v for k, v in record["controller"].items() if k not in ("type", "params_recorded")} == expected_params
        assert record["candidate_index"] == (selected["candidate_index"] if record["phase"] == "tuned" else 0)
        assert digest(suite / record["input_file"]) == record["input_sha256"]
        assert digest(suite / record["trace_file"]) == record["trace_file_sha256"]
        inputs = read(suite / record["input_file"])
        assert inputs["scenario"] == record["scenario"]
        assert inputs["parameter_factor"] == record["parameter_factor"]
        if record["subset"] == "heldout":
            case = tuple(record[k] for k in ("model_name", "controller_name", "phase", "family", "parameter_factor", "seed"))
            assert case not in actual_cases
            actual_cases.add(case)
            paired_key = tuple(record[k] for k in ("model_name", "family", "parameter_factor", "seed"))
            input_pairing.setdefault(paired_key, set()).add(record["input_sha256"])
        else:
            candidate = logs[name][record["candidate_index"]]
            original = next(c for c in candidate["training"] if c["scenario"] == record["family"])
            assert record["trajectory_sha256"] == original["trajectory_sha256"]
        if record["metrics"]["status"] != "completed":
            raise AssertionError("Audit requires complete raw traces; failed records retained: "+record["case_id"])
        with (suite / record["trace_file"]).open(encoding="utf8", newline="") as stream:
            rows = [{k: float(v) if k not in ("action_taken", "transition_completed") and v else v for k, v in row.items()} for row in csv.DictReader(stream)]
        s = record["scenario"]
        assert len(rows) == round(s["duration_s"]/s["dt_s"])+1
        assert rows[-1]["applied_input"] == "" and rows[-1]["interval_s"] == 0
        evaluated = [r for r in rows if r["time_s"] >= s["evaluation_start_s"]-1e-12 and r["interval_s"] > 0]
        duration = sum(r["interval_s"] for r in evaluated)
        iae = sum(abs(r["reference"]-r["output"])*r["interval_s"] for r in evaluated)
        rmse = math.sqrt(sum((r["reference"]-r["output"])**2*r["interval_s"] for r in evaluated)/duration)
        variation = sum(abs(b["applied_input"]-a["applied_input"]) for a, b in zip(evaluated, evaluated[1:]))
        saturation = sum(r["interval_s"] for r in evaluated if abs(r["requested_input"]-r["applied_input"]) > 1e-10)/duration
        values = dict(iae=iae, rmse=rmse, input_total_variation=variation, saturation_fraction=saturation,
            normalized_iae=iae/(record["reference_scale"]*(s["duration_s"]-s["evaluation_start_s"])),
            normalized_rmse=rmse/record["reference_scale"],
            input_variation_rate=variation/(record["input_limit"]*(s["duration_s"]-s["evaluation_start_s"])))
        for key, v in values.items():
            error = abs(v-record["metrics"][key])
            assert error <= 1e-10+1e-10*abs(v), (record["case_id"], key, error)
            metric_errors.append(error)
        checked += 1
    assert actual_cases == expected_cases
    assert all(len(hashes) == 1 for hashes in input_pairing.values())
    assert training_runs+len(actual_cases) == status["written_runs"] == status["expected_runs"]
    assert checked == manifest["raw_trace_runs"]
    return dict(passed=True, selected_groups=len(selection), training_runs=training_runs, heldout_runs=len(actual_cases),
                raw_traces_checked=checked, paired_inputs_checked=len(input_pairing), max_metric_abs_error=max(metric_errors),
                selection_sha256=sha, audit_script_sha256=digest(Path(__file__)),
                scope="artifact consistency, training-only selection and CSV metric recomputation; not a hardware validation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.suite)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
