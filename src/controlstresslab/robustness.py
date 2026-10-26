"""Finite full-factorial SISO scans with frozen controllers and paired noise seeds."""
import argparse
from copy import deepcopy
from dataclasses import asdict
import html
import itertools
import json
import math
from pathlib import Path

from . import analysis_artifacts as artifacts
from .benchmark_design import controller_for, spec_for
from .cli import write_csv
from .coverage import COLUMN_MAP, neutral_metrics
from .experiment import (Cancelled, MODELS, atomic_json, default_config as experiment_config,
    finite_tree, keys, scenario_for, sha, plant_for_config, spec_for_config, validate_config as validate_experiment)
from .simulation import simulate
from .linear_models import save_snapshot

MAX_RUNS = 1000
MAX_INTERVALS = 2_000_000
METRICS = ("rmse", "iae", "input_total_variation", "saturation_fraction")
THRESHOLDS = {"rmse_max": "rmse", "saturation_fraction_max": "saturation_fraction", "input_variation_rate_max": "input_variation_rate"}
CLASS_LABELS = {"met": "满足要求", "not_met": "未满足要求", "run_failed": "运行失败", "incomplete": "未完成"}
AXIS_LABELS = {"plant.gain_scale": "控制增益尺度", "plant.time_scale": "模型时间尺度", "plant.gain": "增益", "plant.tau_s": "时间常数 / s", "plant.mass_kg": "质量 / kg",
    "plant.damping_N_s_m": "阻尼 / (N·s/m)", "plant.stiffness_N_m": "刚度 / (N/m)",
    "conditions.noise_std": "噪声标准差", "conditions.measurement_delay_s": "测量延迟 / s", "disturbance.amplitude": "扰动幅值"}


def allowed_axes(model):
    names = ("plant.gain_scale", "plant.time_scale") if model == "transfer_function" else ("plant.gain", "plant.tau_s") if model == "first_order" else ("plant.mass_kg", "plant.damping_N_s_m", "plant.stiffness_N_m")
    return {k: AXIS_LABELS[k] for k in (*names, "conditions.noise_std", "conditions.measurement_delay_s", "disturbance.amplitude")}


def default_config(base=None):
    base = deepcopy(base) if base is not None else experiment_config()
    key = "plant.time_scale" if base["model"] == "transfer_function" else "plant.tau_s" if base["model"] == "first_order" else "plant.mass_kg"
    nominal = base["plant"]["time_scale"] if base["model"] == "transfer_function" else 1.0
    return dict(schema="robustness-1.0", base=base, axes=[dict(key=key, values=[0.5*nominal, nominal, 1.5*nominal]),
        dict(key="conditions.measurement_delay_s", values=[0.0, 0.05, 0.1])], seeds=[42], max_runs=500,
        thresholds=dict(rmse_max=0.25, saturation_fraction_max=0.25, input_variation_rate_max=None))


def case_configs(config):
    axes = config["axes"]
    ys = list(enumerate(axes[1]["values"])) if len(axes) == 2 else [(0, None)]
    for (xi, xv), (yi, yv), seed in itertools.product(enumerate(axes[0]["values"]), ys, config["seeds"]):
        value = deepcopy(config["base"])
        for axis, level in zip(axes, (xv, yv)):
            group, field = axis["key"].split(".")
            value[group][field] = level
        value["conditions"]["seed"] = seed
        yield xi, yi, seed, value


def validate_config(value):
    finite_tree(value)
    keys(value, default_config(), "扫描")
    c = deepcopy(value)
    if c["schema"] != "robustness-1.0": raise ValueError("未知扫描配置版本")
    c["base"] = validate_experiment(c["base"])
    axes = c["axes"]
    if not isinstance(axes, list) or not 1 <= len(axes) <= 2: raise ValueError("选择1或2条扫描轴")
    selected = []
    for axis in axes:
        keys(axis, ("key", "values"), "扫描轴")
        if not isinstance(axis["key"], str) or axis["key"] not in allowed_axes(c["base"]["model"]): raise ValueError("扫描轴与对象不匹配")
        selected.append(axis["key"])
        levels = axis["values"]
        if not isinstance(levels, list) or not 1 <= len(levels) <= 21 or any(type(x) not in (int, float) or not math.isfinite(x) for x in levels):
            raise ValueError("每条轴需要1～21个有限实数")
        if any(a >= b for a, b in zip(levels, levels[1:])): raise ValueError("轴取值必须严格递增，不自动排序或取整")
    if len(set(selected)) != len(selected): raise ValueError("两条扫描轴不能相同")
    if "disturbance.amplitude" in selected and c["base"]["disturbance"]["kind"] == "constant": raise ValueError("常值扰动使用偏置，请先改为阶跃等幅值波形")
    seeds = c["seeds"]
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 10 or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("使用1～10个不同的非负整数噪声种子")
    if type(c["max_runs"]) is not int or not 1 <= c["max_runs"] <= MAX_RUNS: raise ValueError("运行预算须为1～1000整数")
    count = math.prod(len(a["values"]) for a in axes)*len(seeds)*len(c["base"]["selected_controllers"])
    if count > c["max_runs"]: raise ValueError(f"计划{count}次运行，超过声明预算{c['max_runs']}")
    intervals = round(c["base"]["conditions"]["duration_s"]/c["base"]["conditions"]["dt_s"])
    if count*intervals > MAX_INTERVALS: raise ValueError("总采样推进区间超过200万，请缩小网格或缩短时长")
    keys(c["thresholds"], THRESHOLDS, "要求阈值")
    enabled = False
    for key, threshold in c["thresholds"].items():
        if threshold is None: continue
        enabled = True
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0 or (key == "saturation_fraction_max" and threshold > 1):
            raise ValueError("阈值须为非负有限数，饱和比例上限不超过1")
    if not enabled: raise ValueError("至少预先声明一个要求阈值")
    # Validate every cell before creating any output. No controller retuning.
    for _, _, _, case in case_configs(c): validate_experiment(case)
    return c


def run_count(config):
    return math.prod(len(a["values"]) for a in config["axes"])*len(config["seeds"])*len(config["base"]["selected_controllers"])


def classify(metrics, thresholds):
    if metrics["status"] != "completed": return "run_failed"
    return "met" if all(metrics[THRESHOLDS[k]] is not None and metrics[THRESHOLDS[k]] <= v for k, v in thresholds.items() if v is not None) else "not_met"


def summarize(records, config):
    cells = []
    nx = len(config["axes"][0]["values"])
    ny = len(config["axes"][1]["values"]) if len(config["axes"]) == 2 else 1
    for name, yi, xi in itertools.product(config["base"]["selected_controllers"], range(ny), range(nx)):
        group = [r for r in records if r["controller_name"] == name and r["axis_indices"] == [xi, yi]]
        count = len(group)
        complete = count == len(config["seeds"]) and {r["seed"] for r in group} == set(config["seeds"])
        failures = sum(r["metrics"]["status"] != "completed" for r in group)
        state = "incomplete" if not complete else "run_failed" if failures else "not_met" if any(r["requirement"] == "not_met" for r in group) else "met"
        values = {k: max(r["metrics"][k] for r in group) if complete and not failures and all(r["metrics"][k] is not None for r in group) else None for k in METRICS}
        cells.append(dict(controller_name=name, axis_indices=[xi, yi], observed_seeds=count, expected_seeds=len(config["seeds"]), failed_runs=failures,
            requirement=state, worst_observed=values, case_ids=[r["case_id"] for r in group]))
    worst = {}
    for name in config["base"]["selected_controllers"]:
        group = [r for r in records if r["controller_name"] == name and r["metrics"]["rmse"] is not None and r["metrics"]["status"] == "completed"]
        worst[name] = max(group, key=lambda r: r["metrics"]["rmse"])["case_id"] if group else None
    return dict(aggregation="max_over_declared_noise_seeds; any_failed_run_masks_numeric_cell", cells=cells,
        worst_completed_rmse_case=worst, failed_runs=sum(r["metrics"]["status"] != "completed" for r in records),
        scope="finite_declared_grid_only; no_global_worst_case_or_robust_stability_claim; grid_points_are_not_IID_replicates")


def execute(output, value, *, plots=False, progress=None, should_cancel=None):
    config = validate_config(value)
    expected, records, failed = run_count(config), [], 0
    output, manifest = artifacts.begin(output, "robustness-1.0", config, expected)
    manifest.update(design="full_factorial", pairing="within cell and seed: identical sampled signals/noise; controllers frozen across grid",
        noise_seeds="paired across cells; same standard-normal basis with configured scaling; waveform seeds remain frozen",
        grid_interpretation="finite grid; supplied noise seeds; no real-world failure probability or continuous-domain stability proof")
    def checkpoint(stage):
        if should_cancel and should_cancel(): raise Cancelled("扫描已取消，已有完整记录保留")
        if progress: progress(dict(event="progress", stage=stage, written=len(records), expected=expected, failed=failed))
    try:
        for sub in ("inputs", "runs"): (output/sub).mkdir()
        atomic_json(output/"config.json", config)
        atomic_json(output/"manifest.json", manifest)
        write_csv(output/"plan.csv", [dict(case_id=f"x{x}_y{y}_seed{seed}_{name}",x_index=x,y_index=y,seed=seed,controller=name,
            **{a["key"]:a["values"][i] for a,i in zip(config["axes"],(x,y))})
            for x,y,seed,_ in case_configs(config) for name in config["base"]["selected_controllers"]])
        for xi, yi, seed, case in case_configs(config):
            checkpoint(f"工况 ({xi+1}, {yi+1}) / seed {seed}")
            s = scenario_for(case)
            spec = dict(spec_for_config(case), scale=case["conditions"]["reference_scale"], limit=s.voltage_limit)
            frozen_model=save_snapshot(output,case)
            input_file = f"inputs/x{xi}_y{yi}_seed{seed}.json"
            atomic_json(output/input_file, dict(scenario=asdict(s), noise=s.noise_sequence(), units=spec["units"]))
            input_sha = sha(output/input_file)
            for name in case["selected_controllers"]:
                checkpoint(f"工况 ({xi+1}, {yi+1}) / seed {seed} / {name}")
                params = next(d["parameters"] for d in case["controllers"] if d["name"] == name)
                run = simulate(plant_for_config(case), controller_for(name, params), s)
                metrics = neutral_metrics(run, spec)
                metrics["input_variation_rate"] = None if metrics["normalized_input_variation"] is None else metrics["normalized_input_variation"]/(s.duration_s-s.evaluation_start_s)
                case_id = f"x{xi}_y{yi}_seed{seed}_{name}"
                trace = "runs/"+case_id+".csv"
                write_csv(output/trace, [{new: row[old] for new, old in COLUMN_MAP.items()} for row in run.rows])
                record = dict(**frozen_model, case_id=case_id, model_name=case["model"], controller_name=name, axis_indices=[xi, yi],
                    axis_values=[axis["values"][i] for axis, i in zip(config["axes"], (xi, yi))], seed=seed,
                    run_config=case, plant=run.plant, controller=run.controller, scenario=asdict(s), units=spec["units"],
                    reference_scale=spec["scale"], input_limit=s.voltage_limit, input_file=input_file, input_sha256=input_sha,
                    trace_file=trace, trace_file_sha256=sha(output/trace), metrics=metrics, failure=run.failure,
                    requirement=classify(metrics, config["thresholds"]))
                atomic_json(output/("runs/"+case_id+".json"), record)
                records.append(record)
                failed += metrics["status"] != "completed"
                artifacts.checkpoint(output, manifest, records, failed)
        checkpoint("汇总网格与保存图表")
        summary = summarize(records, config)
        atomic_json(output/"summary.json", summary)
        write_csv(output/"summary.csv", [dict(case_id=r["case_id"], controller=r["controller_name"], x_index=r["axis_indices"][0], y_index=r["axis_indices"][1], seed=r["seed"], requirement=r["requirement"], **r["metrics"]) for r in records])
        if plots:
            from .robustness_plots import build
            build(output, summary, config)
        checkpoint("保存报告与完整性清单")
        rows = "".join(f'<tr><td><a href="{r["trace_file"]}">{r["case_id"]}</a></td><td>{html.escape(str(r["axis_values"]))}</td><td>{CLASS_LABELS[r["requirement"]]}</td><td>{r["metrics"]["rmse"]}</td><td>{html.escape(r["metrics"].get("reason", ""))}</td></tr>' for r in records)
        images = "".join(f'<a href="figures/{p.name}"><img src="figures/{p.name}"></a>' for p in sorted((output/"figures").glob("*.png")))
        (output/"report.html").write_text(f'''<!doctype html><meta charset="utf-8"><title>ControlStressLab 通用参数扫描</title>
<style>body{{font:16px sans-serif;max-width:1250px;margin:30px auto;padding:20px;line-height:1.7}}td,th{{padding:7px;border:1px solid #ddd}}table{{border-collapse:collapse}}img{{max-width:100%}}</style>
<h1>通用参数扫描与要求检查</h1><p>共{expected}次，运行失败{failed}次。控制器参数在全部网格中冻结；相同工况/种子共享信号与噪声。</p>
<p>热力图数值为声明噪声种子中的最大观察值；任一种子运行失败则该格数值留空并标记失败。满足要求仅表示本次预先声明的阈值。</p>
<p>有限网格不保证连续参数范围的真正最坏情况，不证明鲁棒稳定性；网格点不是IID重复样本，种子结果不代表现实失效概率。全部为合成仿真。</p>
<p>输出单位：{html.escape(spec['units']['output'])}；输入单位：{html.escape(spec['units']['input'])}；评价窗口：{s.evaluation_start_s}—{s.duration_s}s。</p>
<p><a href="config.json">冻结配置/轴/种子/阈值</a> · <a href="summary.json">逐格汇总及最差已完成工况</a> · <a href="summary.csv">逐次指标</a> · <a href="manifest.json">源码与设计</a> · <a href="status.json">状态</a></p>{images}
<table><tr><th>原始轨迹</th><th>轴值</th><th>要求检查</th><th>RMSE</th><th>终止原因</th></tr>{rows}</table>''', encoding="utf8")
        artifacts.finish(output, manifest, records, failed)
        return output/"report.html", failed
    except BaseException as exc:
        artifacts.interrupted(output, manifest, records, failed, exc)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf8")) if args.config else default_config()
    report, failed = execute(args.output, config, plots=args.plots)
    print(report)
    if failed: parser.exit(1)


if __name__ == "__main__": main()
