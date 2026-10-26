"""Auditable finite-candidate search, raw traces and transactional reports."""
import argparse
from copy import deepcopy
from dataclasses import asdict
import html
import json
from pathlib import Path

from . import analysis_artifacts as artifacts
from .benchmark_design import controller_for, spec_for
from .cli import write_csv
from .coverage import COLUMN_MAP, neutral_metrics
from .experiment import Cancelled, MODELS, atomic_json, scenario_for, sha, plant_for_config, spec_for_config
from .simulation import simulate
from .linear_models import save_snapshot
from .tuning_objectives import checks, summarize
from .tuning_protocol import default_config, input_payload, prepare


def checkpoint(stage, records, expected, progress, should_cancel):
    if should_cancel and should_cancel(): raise Cancelled("整定任务已取消，已有记录保留；不产生完整结论")
    if progress: progress(dict(event="progress",stage=stage,written=len(records),expected=expected))


def source_snapshot(output):
    target = output/"source"
    target.mkdir()
    for p in sorted(Path(__file__).parent.glob("*.py")): (target/p.name).write_bytes(p.read_bytes())


def run_cases(output, config, cases, candidates, records, manifest, stage, progress, should_cancel, roles=None):
    for case in cases:
        value = case["run_config"]
        s = scenario_for(value)
        spec = dict(spec_for_config(value),scale=value["conditions"]["reference_scale"],limit=s.voltage_limit)
        frozen_model=save_snapshot(output,value)
        input_file = f"inputs/{case['case_id']}.json"
        atomic_json(output/input_file,dict(scenario=asdict(s),noise=s.noise_sequence(),payload=input_payload(value),units=spec["units"]))
        input_file_sha = sha(output/input_file)
        for candidate in candidates:
            cid = candidate["candidate_id"]
            checkpoint(f"{stage} / {case['family']} / 工况{case['condition_index']+1} / 候选{cid}",records,manifest["expected_runs"],progress,should_cancel)
            v = deepcopy(value)
            for definition in v["controllers"]:
                if definition["name"] == config["controller"]: definition["parameters"] = deepcopy(candidate["parameters"])
            run = simulate(plant_for_config(v),controller_for(config["controller"],candidate["parameters"]),s)
            m = neutral_metrics(run,spec)
            m["input_variation_rate"] = None if m["normalized_input_variation"] is None else m["normalized_input_variation"]/(s.duration_s-s.evaluation_start_s)
            case_id = f"c{cid}_{case['case_id']}"
            trace = f"runs/{case_id}.csv"
            write_csv(output/trace,[{new:row[old] for new,old in COLUMN_MAP.items()} for row in run.rows])
            issues = checks(m,config["thresholds"])
            record = dict(**frozen_model,case_id=case_id,candidate_id=cid,subset=stage,model_name=v["model"],controller_name=config["controller"],
                family=case["family"],condition_index=case["condition_index"],input_index=case["input_index"],point=case["point"],
                seed=case["seed"],parameter_factor=str(case["point"]),run_config=v,plant=run.plant,controller=run.controller,
                scenario=asdict(s),units=spec["units"],reference_scale=spec["scale"],input_limit=s.voltage_limit,
                input_file=input_file,input_sha256=input_file_sha,stimulus_sha256=case["input_sha256"],contract_sha256=case["contract_sha256"],
                trace_file=trace,trace_file_sha256=sha(output/trace),metrics=m,failure=run.failure,issues=issues,
                requirement="met" if not issues else issues[0]["kind"],roles=(roles or {}).get(cid,[]))
            atomic_json(output/f"runs/{case_id}.json",record)
            records.append(record)
            artifacts.checkpoint(output,manifest,records,sum(r["metrics"]["status"]!="completed" for r in records))


def report(output, title, summary, records, config):
    figures = "".join(f'<a href="figures/{p.name}"><img src="figures/{p.name}" loading="lazy"></a>' for p in sorted((output/"figures").glob("*.png")))
    rows = "".join(f'<tr><td><a href="{r["trace_file"]}">{r["case_id"]}</a></td><td>{r["requirement"]}</td>'
        f'<td>{html.escape(json.dumps(r["point"],ensure_ascii=False))}</td><td>{r["metrics"]["normalized_rmse"]}</td>'
        f'<td>{r["metrics"]["input_variation_rate"]}</td><td>{html.escape(json.dumps(r["issues"],ensure_ascii=False))}</td></tr>' for r in records)
    decision = ""
    if "frontier_ids" in summary: decision = f'可行候选{summary["feasible_count"]}个；有限候选非支配ID：{summary["frontier_ids"]}。未找到可行候选时不回退、不启动验证。'
    elif "main_candidate_id" in summary: decision = f'事先主选候选{summary["main_candidate_id"]}；主选要求检查：{summary["main_outcome"]}；验证不重新选择参数。'
    (output/"report.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:16px sans-serif;max-width:1300px;margin:24px auto;padding:20px;line-height:1.7}}img{{max-width:100%}}table{{border-collapse:collapse;font-size:12px}}td,th{{border:1px solid #ddd;padding:6px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style>
<h1>{html.escape(title)}</h1><p>{html.escape(decision)}</p>
<p>全部为合成模型。要求针对声明的有限工况，不能推断真实设备可靠性、全局最优或连续参数域鲁棒稳定性。V=实际输入总变化量/(限幅×评价时长)，单位1/s，不代表能耗。</p>
<p>搜索误差目标按每个工况最坏种子、族内等权、族间等权汇总；动作目标取全工况最大值。失败或越限不参与可行候选前沿。参考尺度、阈值、窗口、参数范围与种子在运行前固定。</p>
<p><a href="config.json">冻结协议</a> · <a href="summary.json">阶段结论</a> · <a href="plan.json">运行计划</a> · <a href="summary.csv">逐次指标</a> · <a href="manifest.json">来源与源码</a> · <a href="status.json">文件/执行状态</a></p>
<h2>要求与阶段依据</h2><pre>{html.escape(json.dumps(dict(thresholds=config['thresholds'],summary=summary),ensure_ascii=False,indent=2))}</pre>
{figures}<table><tr><th>原始轨迹</th><th>状态</th><th>工况</th><th>归一化RMSE</th><th>动作变化率/s</th><th>不满足项</th></tr>{rows}</table></html>''',encoding="utf8")


def finalize(output, manifest, config, summary, records, plots, progress, should_cancel):
    checkpoint("保存原始指标与图表",records,manifest["expected_runs"],progress,should_cancel)
    atomic_json(output/"summary.json",summary)
    write_csv(output/"summary.csv",[dict(case_id=r["case_id"],candidate_id=r["candidate_id"],family=r["family"],condition_index=r["condition_index"],
                                       input_index=r["input_index"],requirement=r["requirement"],**r["metrics"]) for r in records])
    if plots:
        from .tuning_plots import build
        build(output,summary,records)
    checkpoint("保存报告与完整性清单",records,manifest["expected_runs"],progress,should_cancel)
    report(output,"ControlStressLab · "+("约束多目标搜索" if "frontier_ids" in summary else "冻结后的新工况验证"),summary,records,config)
    failed = sum(r["metrics"]["status"]!="completed" for r in records)
    manifest.update(execution_complete=True,requirements_met=bool(summary["feasible_count"]) if "feasible_count" in summary else summary["main_outcome"]=="met")
    artifacts.finish(output,manifest,records,failed)
    return output/"report.html",failed


def execute(output, value=None, *, plots=False, progress=None, should_cancel=None):
    plan = prepare(default_config() if value is None else value)
    config, records = plan["config"], []
    from .tuning_validation import check_unobserved
    check_unobserved(Path(output).resolve().parent,[c["input_sha256"] for c in plan["validation"]])
    checkpoint("协议与预算已校验",records,plan["budget"]["search_runs"],progress,should_cancel)
    output,manifest = artifacts.begin(output,"tuning-search-1.0",config,plan["budget"]["search_runs"])
    manifest.update(execution_complete=False,requirements_met=None,observation_registry=str(output.parent/"tuning-observations.json"))
    try:
        for name in ("inputs","runs"): (output/name).mkdir()
        atomic_json(output/"config.json",config)
        atomic_json(output/"plan.json",plan)
        atomic_json(output/"candidates.json",dict(candidates=plan["candidates"],aliases=plan["aliases"]))
        atomic_json(output/"manifest.json",manifest)
        source_snapshot(output)
        run_cases(output,config,plan["search"],plan["candidates"],records,manifest,"search",progress,should_cancel)
        summary = summarize(plan["candidates"],records,config,len(plan["search"]))
        summary["budget"] = plan["budget"]
        return finalize(output,manifest,config,summary,records,plots,progress,should_cancel)
    except BaseException as exc:
        artifacts.interrupted(output,manifest,records,sum(r["metrics"]["status"]!="completed" for r in records),exc)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--plots",action="store_true")
    args = parser.parse_args()
    value = json.loads(args.config.read_text(encoding="utf8")) if args.config else None
    saved,failed = execute(args.output,value,plots=args.plots)
    print(saved)
    if failed: parser.exit(1)


if __name__ == "__main__": main()
