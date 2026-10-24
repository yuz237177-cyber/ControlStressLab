"""Deterministic parameter grids with fixed controller gains and explicit provenance."""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import html
import json
import math
from numbers import Real
from pathlib import Path
import sys

from . import __version__
from .cli import batch_status, demo_scenarios, write_csv, write_json
from .controllers import PID
from .metrics import evaluate
from .models import DCMotor
from .simulation import parameters, simulate

LEVELS = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
SCENARIOS = ("nominal", "load_step")


@dataclass(frozen=True)
class SweepPlan:
    inertia_factors: tuple[float, ...] = LEVELS
    friction_factors: tuple[float, ...] = LEVELS
    dt_s: float = 0.01
    kp: float = 0.25
    ki: float = 0.8
    kd: float = 0.0

    def __post_init__(self):
        for name in ("inertia_factors", "friction_factors"):
            values = tuple(getattr(self, name))
            if not values or any(isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x) or x <= 0 for x in values):
                raise ValueError(f"{name} must contain finite positive real factors")
            if any(a >= b for a, b in zip(values, values[1:])) or 1.0 not in values:
                raise ValueError(f"{name} must be strictly increasing and include the nominal factor 1")
            object.__setattr__(self, name, tuple(float(x) for x in values))
        if self.expected_runs > 2000:
            raise ValueError("uncertainty sweep exceeds the 2000 run limit")
        PID(kp=self.kp, ki=self.ki, kd=self.kd)
        demo_scenarios(self.dt_s, 42)
        nominal = DCMotor()
        for j in self.inertia_factors:
            for b in self.friction_factors:
                DCMotor(inertia_kg_m2=nominal.inertia_kg_m2 * j, friction_Nm_s=nominal.friction_Nm_s * b)

    @property
    def expected_runs(self):
        return len(self.inertia_factors) * len(self.friction_factors) * len(SCENARIOS) * 2


def cases(plan: SweepPlan):
    nominal = DCMotor()
    scenarios = [s for s in demo_scenarios(plan.dt_s, 42) if s.name in SCENARIOS]
    for ji, j in enumerate(plan.inertia_factors):
        for bi, b in enumerate(plan.friction_factors):
            for label, anti in (("pid", False), ("pid_antiwindup", True)):
                reference_run = None
                for scenario in scenarios:
                    plant = DCMotor(inertia_kg_m2=nominal.inertia_kg_m2 * j, friction_Nm_s=nominal.friction_Nm_s * b)
                    damping = plant.friction_Nm_s + plant.torque_Nm_A * plant.back_emf_V_s / plant.resistance_ohm
                    run = simulate(plant, PID(kp=plan.kp, ki=plan.ki, kd=plan.kd, anti_windup=anti), scenario)
                    record = {"case_id": f"{scenario.name}__{label}__j{ji:02d}_b{bi:02d}", "scenario": scenario.name,
                              "controller_name": label, "inertia_factor": j, "friction_factor": b,
                              "plant": run.plant, "controller": run.controller, "metrics": evaluate(run),
                              "derived": {"damping_Nm_s": damping, "time_constant_s": plant.inertia_kg_m2 / damping,
                                          "dc_gain_rad_s_per_V": plant.torque_Nm_A / plant.resistance_ohm / damping},
                              "trace_sha256": hashlib.sha256(json.dumps(run.rows, allow_nan=False).encode("utf8")).hexdigest(),
                              "trace_file": None, "failure": run.failure}
                    record["record_file"] = record["case_id"] + ".json"
                    record["post_iae_ratio_to_own_nominal"] = None
                    record["incremental_load_iae_rad"] = None
                    record["incremental_load_effect_status"] = "not_applicable"
                    if scenario.name == "nominal":
                        reference_run = run
                    elif record["metrics"]["status"] == "completed" and reference_run is not None and evaluate(reference_run)["status"] == "completed":
                        # Difference of paired output trajectories, NOT a difference of two IAEs.
                        value = sum(abs(a["true_output_rad_s"] - b["true_output_rad_s"]) * a["interval_s"]
                                    for a, b in zip(run.rows, reference_run.rows)
                                    if a["time_s"] >= scenario.recovery_start_s - 1e-12 and a["transition_completed"])
                        record["incremental_load_iae_rad"] = value if math.isfinite(value) else None
                        record["incremental_load_effect_status"] = "available" if math.isfinite(value) else "nonfinite"
                    else:
                        record["incremental_load_effect_status"] = "paired_run_incomplete"
                    yield record, run


def summarize(records: list[dict]) -> list[dict]:
    groups = []
    for scenario in SCENARIOS:
        for label in ("pid", "pid_antiwindup"):
            subset = [r for r in records if r["scenario"] == scenario and r["controller_name"] == label]
            baseline = next(r for r in subset if r["inertia_factor"] == r["friction_factor"] == 1.0)
            denominator = baseline["metrics"]["iae_post_event_rad"]
            valid = [r for r in subset if r["metrics"]["status"] == "completed"]
            for record in subset:
                value = record["metrics"]["iae_post_event_rad"]
                ratio = value / denominator if value is not None and denominator is not None and denominator > 0 else None
                record["post_iae_ratio_to_own_nominal"] = ratio if ratio is not None and math.isfinite(ratio) else None
            worst = max(valid, key=lambda r: r["metrics"]["iae_post_event_rad"], default=None)
            groups.append({"scenario": scenario, "controller_name": label, "sampled_points": len(subset),
                           "completed": len(valid), "failed": len(subset) - len(valid),
                           "not_recovered": sum(r["metrics"]["recovery_status"] == "not_recovered_in_observation_window" for r in valid),
                           "nominal_case": baseline["case_id"], "nominal_post_iae_rad": denominator,
                           "worst_valid_sampled_case": worst["case_id"] if worst else None,
                           "max_valid_sampled_post_iae_rad": worst["metrics"]["iae_post_event_rad"] if worst else None})
    return groups


def execute_sweep(output: Path, plan: SweepPlan | None = None, *, plots: bool = False, save_all_traces: bool = False) -> Path:
    plan = plan or SweepPlan()
    if plots:
        import matplotlib  # Optional; refuse before creating output if unavailable.
    output.mkdir(parents=True, exist_ok=False)
    records, selected = [], {}
    failed = 0
    try:
        write_json(output / "status.json", batch_status("in_progress", plan.expected_runs, 0, 0))
        write_json(output / "plan.json", {"feature": "parameter_uncertainty_development", "design": asdict(plan),
                   "scenarios": [asdict(s) for s in demo_scenarios(plan.dt_s, 42) if s.name in SCENARIOS],
                   "expected_runs": plan.expected_runs, "evidence": "synthetic_assumption",
                   "domain_is_hardware_tolerance": False, "probability_distribution": None,
                   "controller_retuning": False, "replication": "deterministic grid, no independent replicates"})
        for record, run in cases(plan):
            if save_all_traces:
                name = record["case_id"] + ".csv"
                write_csv(output / name, run.rows)
                record["trace_file"] = name
            write_json(output / record["record_file"], record)
            records.append(record)
            failed += record["metrics"]["status"] != "completed"
            key = (record["scenario"], record["controller_name"])
            if record["inertia_factor"] == record["friction_factor"] == 1.0:
                selected[(*key, "nominal")] = (record, run.rows)
            if record["metrics"]["status"] == "completed":
                previous = selected.get((*key, "worst"))
                if previous is None or record["metrics"]["iae_post_event_rad"] > previous[0]["metrics"]["iae_post_event_rad"]:
                    selected[(*key, "worst")] = (record, run.rows)
            write_json(output / "status.json", batch_status("in_progress", plan.expected_runs, len(records), failed))
        for record, rows in selected.values():
            if record["trace_file"] is None:
                name = record["case_id"] + ".csv"
                write_csv(output / name, rows)
                record["trace_file"] = name
        groups = summarize(records)
        for record in records:
            write_json(output / record["record_file"], record)
        write_csv(output / "summary.csv", [{"case_id": r["case_id"], "scenario": r["scenario"],
                  "controller_name": r["controller_name"], "inertia_factor": r["inertia_factor"], "friction_factor": r["friction_factor"],
                  "inertia_kg_m2": r["plant"].get("inertia_kg_m2"), "friction_Nm_s": r["plant"].get("friction_Nm_s"),
                  **r["derived"], **r["metrics"], "post_iae_ratio_to_own_nominal": r["post_iae_ratio_to_own_nominal"],
                  "incremental_load_iae_rad": r["incremental_load_iae_rad"], "incremental_load_effect_status": r["incremental_load_effect_status"],
                  "trace_file": r["trace_file"]} for r in records])
        write_json(output / "manifest.json", {"project_version": __version__, "schema_version": "uncertainty-1.0",
                   "feature": "parameter_uncertainty_development",
                   "status_authority": "status.json", "python": sys.version, "evidence": "synthetic_assumption",
                   "hardware_validated": False, "plan": asdict(plan), "nominal_plant": parameters(DCMotor()),
                   "source_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))},
                   "groups": groups, "cases": records})
        figures = []
        if plots:
            from .uncertainty_plots import render
            figures = render(output, records, plan)
        lines = []
        for group in groups:
            lines.append("<tr>" + "".join(f"<td>{html.escape(str(group[k]))}</td>" for k in
                         ("scenario", "controller_name", "sampled_points", "nominal_post_iae_rad", "max_valid_sampled_post_iae_rad", "not_recovered", "failed")) + "</tr>")
        images = "".join(f'<section><h2>{html.escape(title)}</h2><a href="{stem}.svg"><img src="{stem}.png" alt="{html.escape(title)}"></a></section>' for stem, title in figures)
        report = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                  '<title>ControlStressLab 参数不确定性分析</title><style>body{font:16px system-ui;max-width:1120px;margin:32px auto;padding:0 20px;color:#172033}'
                  'table{border-collapse:collapse;display:block;overflow:auto}td,th{border:1px solid #ddd;padding:9px}img{width:100%;height:auto}.note{background:#fff4d5;padding:16px}</style>'
                  '<h1>参数不确定性分析 · 固定控制器增益</h1><p class="note">合成仿真，未经硬件验证。J、b按人为设定的网格变化；范围不是实测公差或概率分布。'
                  '每次重新创建对象和控制器；不重新调参。单次运行是记录单位，采样点不是独立重复。</p>'
                  f'<p>共记录 {len(records)} 次，失败 {failed} 次。正常跟踪与负载阶跃分别解释。事件后跟踪误差仍可能包含残余起步瞬态。</p>'
                  '<p>增量负载指标将同参数、同控制器的有/无负载输出逐点相减后取绝对值积分，区间为4至12秒；不是两项IAE相减，也不是稳态抗扰性能的单独证明。</p>'
                  '<p>最大值只覆盖已运行的有效离散网格点，不能解释为连续区域的最坏情况或鲁棒稳定性保证。未恢复、运行失败和指标缺失分别标记，未用0代替。</p>'
                  '<p>机械摩擦b只是总阻尼b+Kt·Ke/R的一部分。J与b相同百分比的变化并不代表相同动态影响。</p>'
                  '<p><a href="plan.json">预先约定的计划</a> · <a href="summary.csv">逐次指标CSV</a> · <a href="manifest.json">配置与轨迹指纹</a> · <a href="status.json">权威完成状态</a></p>'
                  '<table><tr><th>场景</th><th>控制器</th><th>网格点数</th><th>标称事件后IAE/rad</th><th>有效点最大IAE/rad</th><th>未恢复</th><th>失败</th></tr>'
                  + "".join(lines) + '</table>' + images + '</html>')
        (output / "report.html").write_text(report, encoding="utf8", newline="\n")
        state = "completed_with_failures" if failed else "completed"
        final = batch_status(state, plan.expected_runs, len(records), failed, complete=True)
        checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
        checksums["status.json"] = hashlib.sha256(json.dumps(final, indent=2, allow_nan=False).encode("utf8")).hexdigest()
        write_json(output / "checksums.json", checksums)
        write_json(output / "status.json", final)
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        try:
            write_json(output / "status.json", batch_status("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "aborted",
                       plan.expected_runs, len(records), failed, error=exc))
        except OSError:
            print("Unable to update uncertainty status; output may be incomplete.", file=sys.stderr)
        raise
    return output / "report.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/uncertainty"))
    parser.add_argument("--inertia-factors", default=",".join(map(str, LEVELS)))
    parser.add_argument("--friction-factors", default=",".join(map(str, LEVELS)))
    parser.add_argument("--dt", type=float, default=0.01)
    parser.add_argument("--plots", action="store_true", help="requires optional .[charts] dependencies")
    parser.add_argument("--save-all-traces", action="store_true")
    args = parser.parse_args()
    try:
        plan = SweepPlan(tuple(map(float, args.inertia_factors.split(","))), tuple(map(float, args.friction_factors.split(","))), args.dt)
        report = execute_sweep(args.output, plan, plots=args.plots, save_all_traces=args.save_all_traces)
    except (ValueError, FileExistsError, ImportError) as exc:
        parser.error(str(exc))
    status = json.loads((args.output / "status.json").read_text(encoding="utf8"))
    print(f"Parameter grid recorded: {report.resolve()} ({status['written_runs']} runs, {status['failed_runs']} failures)")
    if status["failed_runs"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
