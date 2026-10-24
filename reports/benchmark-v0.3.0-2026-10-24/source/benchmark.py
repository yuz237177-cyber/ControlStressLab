"""Budgeted controller tuning, frozen held-out tests and auditable paired exports."""

import argparse
from dataclasses import asdict
import hashlib
import html
import json
from pathlib import Path
import platform

from . import __version__
from .benchmark_design import (DEFAULT_CONFIG, FAMILIES, TRAINING, assess_candidate, candidate_parameters,
    controller_for, heldout_cases, plant_for, scenario_for, select_candidate, spec_for, validate_config)
from .cli import batch_status, write_csv, write_json
from .coverage import COLUMN_MAP, neutral_metrics
from .simulation import simulate


class SelectionError(ValueError):
    """No feasible training candidate; do not silently substitute a controller."""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics_for(run, spec):
    result = neutral_metrics(run, spec)
    result["input_variation_rate"] = (None if result["normalized_input_variation"] is None else
        result["normalized_input_variation"]/(run.scenario.duration_s-run.scenario.evaluation_start_s))
    return result


def fingerprint(run):
    return hashlib.sha256(json.dumps(run.rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def summarize(records):
    """Family-balanced descriptive summaries; any missing/failed member invalidates a group."""
    groups = {}
    for r in records:
        groups.setdefault((r["model_name"], r["controller_name"], r["phase"]), []).append(r)
    result = []
    for (model, controller, phase), group in groups.items():
        entry = dict(model=model, controller=controller, phase=phase, runs=len(group),
                     failed=sum(r["metrics"]["status"] != "completed" for r in group), families={})
        keys = ("normalized_iae", "normalized_rmse", "input_variation_rate", "saturation_fraction")
        for family in FAMILIES:
            selected = [r for r in group if r["family"] == family]
            ok = selected and all(r["metrics"]["status"] == "completed" for r in selected)
            entry["families"][family] = {k: sum(r["metrics"][k] for r in selected)/len(selected) if ok else None for k in keys}
        entry["comparable"] = not entry["failed"] and all(entry["families"][f]["normalized_iae"] is not None for f in FAMILIES)
        entry.update({k: sum(entry["families"][f][k] for f in FAMILIES)/len(FAMILIES) if entry["comparable"] else None for k in keys})
        result.append(entry)
    return result


def execute(output, config=None, *, plots=False):
    config = validate_config(DEFAULT_CONFIG if config is None else config)
    cases = heldout_cases(config)
    groups = len(config["models"])*len(config["controllers"])
    training_count, heldout_count = groups*config["candidate_budget"]*len(TRAINING), groups*2*len(cases)
    expected = training_count+heldout_count
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    written, failed, records, training, selections, retained = 0, 0, [], [], {}, {}
    manifest = dict(schema_version="benchmark-1.0", package_version=__version__, protocol=config["protocol"],
        config=config, expected_runs=expected, training_runs=training_count, heldout_runs=heldout_count,
        hardware_validated=False, evidence="synthetic_assumption", python=platform.python_version(),
        source_files_sha256={p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
        pairing="same model/case uses identical reference, disturbance, noise, grid, limits; reset every run",
        selection_rule="minimum mean training NIAE among feasible candidates; smaller index breaks ties",
        aggregation="equal weight within each heldout family, then equal weight across four families",
        budget_scope="candidate evaluations, not equal parameter dimension or computation cost",
        training_trace_policy="all candidate metrics/fingerprints; raw CSV for baseline and selected; no reruns",
        artifacts_complete=False)
    write_json(output / "status.json", batch_status("in_progress", expected, written, failed))

    def event(name, **details):
        with (output / "events.jsonl").open("a", encoding="utf8", newline="\n") as stream:
            stream.write(json.dumps(dict(event=name, **details), allow_nan=False)+"\n")

    def save_input(model, case_id, s, factor):
        name = f"inputs/{model}__{case_id}.json"
        spec = spec_for(model)
        write_json(output / name, dict(scenario=asdict(s), noise=s.noise_sequence(), parameter_factor=factor,
            plant_parameters=asdict(plant_for(model, factor)), units=spec["units"], reference_scale=spec["scale"], input_limit=spec["limit"]))
        return name, digest(output / name)

    def save_run(model, name, phase, case, run, input_info, *, subset="heldout", candidate_index=None):
        spec = spec_for(model)
        case_id = f"{subset}__{model}__{name}__{phase}__{case['id']}"
        trace = f"runs/{case_id}.csv"
        write_csv(output / trace, [{new: row[old] for new, old in COLUMN_MAP.items()} for row in run.rows])
        record = dict(case_id=case_id, subset=subset, model_name=model, controller_name=name, phase=phase,
            family=case["family"], parameter_factor=case["factor"], seed=case["seed"], candidate_index=candidate_index,
            plant=run.plant, controller=run.controller, scenario=asdict(run.scenario), units=spec["units"],
            reference_scale=spec["scale"], input_limit=spec["limit"], input_file=input_info[0], input_sha256=input_info[1],
            trace_file=trace, trace_file_sha256=digest(output / trace), trajectory_sha256=fingerprint(run),
            metrics=metrics_for(run, spec), failure=run.failure)
        write_json(output / f"runs/{case_id}.json", record)
        return record

    try:
        for sub in ("inputs", "runs", "training"):
            (output / sub).mkdir()
        write_json(output / "config.json", config)
        manifest["config_sha256"] = digest(output / "config.json")
        write_json(output / "manifest.json", manifest)
        event("training_started", expected_runs=training_count)
        unavailable = []
        for model in config["models"]:
            spec = spec_for(model)
            scenarios = [scenario_for(model, f) for f in TRAINING]
            inputs = [save_input(model, "training_"+f, s, 1.0) for f, s in zip(TRAINING, scenarios)]
            for name in config["controllers"]:
                candidates, best_runs, baseline_runs = [], None, None
                for index, params in enumerate(candidate_parameters(model, name, config)):
                    runs = [simulate(plant_for(model), controller_for(name, params), s) for s in scenarios]
                    metrics = [metrics_for(run, spec) for run in runs]
                    entry = dict(candidate_index=index, parameters=params, assessment=assess_candidate(metrics, config),
                        training=[dict(scenario=f, metrics=m, failure=run.failure, trajectory_sha256=fingerprint(run))
                                  for f, m, run in zip(TRAINING, metrics, runs)])
                    candidates.append(entry)
                    if index == 0: baseline_runs = runs
                    if select_candidate(candidates) is entry: best_runs = runs
                    written += len(runs)
                    failed += sum(m["status"] != "completed" for m in metrics)
                    write_json(output / "status.json", batch_status("in_progress", expected, written, failed))
                key = model+"__"+name
                write_json(output / f"training/{key}.json", candidates)
                training.append(dict(model=model, controller=name, candidates=candidates))
                chosen = select_candidate(candidates)
                if chosen is None:
                    unavailable.append(key)
                    continue
                selections[key] = dict(candidate_index=chosen["candidate_index"], parameters=chosen["parameters"],
                    assessment=chosen["assessment"], baseline_parameters=candidates[0]["parameters"],
                    candidate_count=len(candidates))
                retained[key] = (baseline_runs, best_runs, inputs)
                print(f"Training complete: {key}; selected={chosen['candidate_index']}; feasible={sum(c['assessment']['feasible'] for c in candidates)}/{len(candidates)}", flush=True)
        if unavailable:
            write_json(output / "selection_failure.json", dict(unavailable=unavailable, heldout_started=False))
            raise SelectionError("no feasible candidate: "+", ".join(unavailable))
        write_json(output / "selections.json", selections)
        selection_hash = digest(output / "selections.json")
        manifest["selection_sha256"] = selection_hash
        event("selection_frozen", selection_sha256=selection_hash, selected_groups=len(selections))
        for key, (baseline, tuned, inputs) in retained.items():
            model, name = key.split("__")
            selection = selections[key]
            for phase, runs, index in (("baseline", baseline, 0), ("tuned", tuned, selection["candidate_index"])):
                for f, run, info in zip(TRAINING, runs, inputs):
                    save_run(model, name, phase, dict(id=f, family=f, factor=1, seed=0), run, info,
                             subset="training", candidate_index=index)
        del retained
        event("heldout_started", selection_sha256=selection_hash, expected_runs=heldout_count)
        for model in config["models"]:
            for case in cases:
                if digest(output / "selections.json") != selection_hash:
                    raise ValueError("frozen selection file changed during evaluation")
                s = scenario_for(model, case["family"], case["seed"], heldout=True)
                info = save_input(model, "heldout_"+case["id"], s, case["factor"])
                for name in config["controllers"]:
                    selection = selections[model+"__"+name]
                    for phase, params, index in (("baseline", selection["baseline_parameters"], 0),
                                                ("tuned", selection["parameters"], selection["candidate_index"])):
                        run = simulate(plant_for(model, case["factor"]), controller_for(name, params), s)
                        record = save_run(model, name, phase, case, run, info, candidate_index=index)
                        records.append(record)
                        failed += record["metrics"]["status"] != "completed"
                        written += 1
                        write_json(output / "status.json", batch_status("in_progress", expected, written, failed))
            print(f"Held-out tests complete: {model}; written={written}/{expected}; failed={failed}", flush=True)
        if written != expected: raise ValueError("benchmark run count mismatch")
        summary = summarize(records)
        write_json(output / "summary.json", summary)
        keys = ("case_id", "model_name", "controller_name", "phase", "family", "parameter_factor", "seed", "status",
                "normalized_iae", "normalized_rmse", "input_variation_rate", "saturation_fraction", "recovery_time_s", "recovery_status")
        write_csv(output / "summary.csv", [{k: r.get(k, r["metrics"].get(k)) for k in keys} for r in records])
        if plots:
            from .benchmark_plots import build
            build(output, records, training, summary, config)
        images = "".join(f'<a href="figures/{p.name}"><img src="figures/{p.name}" loading="lazy"></a>' for p in sorted((output / "figures").glob("*.png")))
        rows = "".join(f"<tr><td>{html.escape(r['model'])}</td><td>{r['controller']}</td><td>{r['phase']}</td>"
                       f"<td>{r['normalized_iae']}</td><td>{r['input_variation_rate']}</td><td>{r['failed']}</td></tr>" for r in summary)
        (output / "report.html").write_text(f'''<!doctype html><meta charset="utf-8"><title>ControlStressLab v{__version__} 参数整定与冻结测试</title>
<style>body{{font:16px sans-serif;line-height:1.7;max-width:1300px;margin:24px auto;padding:18px}}img{{max-width:100%}}table{{border-collapse:collapse;font-size:13px}}td,th{{padding:6px;border:1px solid #ccc}}</style>
<h1>ControlStressLab v{__version__}：预算化整定与冻结测试</h1>
<p>训练{training_count}次、冻结测试{heldout_count}次；执行或指标失败{failed}次。合成模型，未进行硬件验证。</p>
<p>每组{config['candidate_budget']}个候选，在3个训练场景按误差和控制动作约束选择；先冻结选择文件，再运行4族未参与选择的测试。基线与整定后共用输入、噪声和物理参数。</p>
<p>汇总先在族内等权，再对4族等权。NIAE=IAE/(参考尺度×评价时长)，动作变化率=TV/(限幅×评价时长)，单位1/s。整组发生失败则不输出可比较的均值，失败不作零误差。</p>
<p>相同候选数不保证不同维度的算法严格公平；有限搜索不证明全局最优。场景与参数因子不是IID样本，没有现实可靠性概率。训练约束不保证在测试中继续满足。</p>
<p>扰动窗口可能含起步残差，不能据此直接宣称纯扰动因果效应；持续变化输入不计算常数恢复时间。</p>
<p>一阶对象单位为unit；二阶代表对象为质量弹簧阻尼，输出m，控制与扰动N。LADRC的b0固定名义值，不随测试tau/m改变。</p>
<p><a href="config.json">实际配置</a> · <a href="selections.json">冻结参数</a> · <a href="events.jsonl">阶段顺序</a> · <a href="summary.csv">逐次指标</a> · <a href="summary.json">族等权汇总</a> · <a href="manifest.json">源码指纹</a> · <a href="status.json">完整性</a></p>
<table><tr><th>对象</th><th>算法</th><th>阶段</th><th>NIAE</th><th>动作变化率 /s</th><th>失败</th></tr>{rows}</table>{images}
<p>全部测试CSV/配置位于runs，全部候选日志位于training。选择文件SHA-256：{selection_hash}</p>''', encoding="utf8", newline="\n")
        event("benchmark_completed", written_runs=written, failed_runs=failed)
        manifest.update(written_runs=written, failed_runs=failed, raw_trace_runs=len(list((output / "runs").glob("*.json"))), artifacts_complete=True)
        write_json(output / "manifest.json", manifest)
        final = batch_status("completed_with_failures" if failed else "completed", expected, written, failed, complete=True)
        status_bytes = json.dumps(final, indent=2, allow_nan=False).encode("utf8")
        hashes = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob("*")) if p.is_file() and p.name != "status.json"}
        hashes["status.json"] = hashlib.sha256(status_bytes).hexdigest()
        write_json(output / "checksums.json", hashes)
        (output / "status.json").write_bytes(status_bytes)
        return output / "report.html", failed
    except BaseException as exc:
        manifest["artifacts_complete"] = False
        for file, data in (("manifest.json", manifest), ("status.json", batch_status(
            "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "export_failure", expected, written, failed, error=exc))):
            try: write_json(output / file, data)
            except Exception: pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="strict JSON configuration; defaults to the documented v0.3 protocol")
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf8")) if args.config else DEFAULT_CONFIG
    report, failed = execute(args.output, config, plots=args.plots)
    print(f"Benchmark report: {report}; failures={failed}")
    if failed: parser.exit(1, "Failed runs preserved; inspect the report.\n")


if __name__ == "__main__": main()
