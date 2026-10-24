"""Fixed-gain load-step x measurement-delay grids, including paired zero-load controls."""

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
from .cli import batch_status, write_csv, write_json
from .controllers import PID
from .metrics import evaluate
from .models import DCMotor
from .simulation import Scenario, StepSignal, simulate

LOADS = tuple(i / 20 for i in range(13))
DELAYS = tuple(i / 20 for i in range(11))
CLASSIFICATIONS = ("recovered", "not_recovered_in_window", "steady_reference_infeasible", "execution_or_metric_failure")


@dataclass(frozen=True)
class StressPlan:
    loads_Nm: tuple[float, ...] = LOADS
    delays_s: tuple[float, ...] = DELAYS
    dt_s: float = 0.01
    duration_s: float = 20.0
    event_s: float = 8.0
    reference_rad_s: float = 60.0
    kp: float = 0.25
    ki: float = 0.8
    kd: float = 0.0

    def __post_init__(self):
        for name in ("loads_Nm", "delays_s"):
            values = tuple(getattr(self, name))
            if not values or any(isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x) or x < 0 for x in values):
                raise ValueError(f"{name} must contain finite nonnegative real values")
            if values[0] != 0 or any(a >= b for a, b in zip(values, values[1:])):
                raise ValueError(f"{name} must be strictly increasing and start with zero")
            object.__setattr__(self, name, tuple(float(x) for x in values))
        if not math.isfinite(self.reference_rad_s) or self.reference_rad_s <= 0:
            raise ValueError("reference_rad_s must be finite and positive")
        if not math.isfinite(self.event_s) or self.event_s < 1:
            raise ValueError("event_s must be at least 1 second")
        PID(kp=self.kp, ki=self.ki, kd=self.kd)
        # Scenario enforces finite time, delay, sample budget and exact grid alignment.
        for delay in self.delays_s:
            self.scenario(self.loads_Nm[-1], delay)
        if self.expected_runs > 2000 or self.expected_runs * round(self.duration_s / self.dt_s) > 5_000_000:
            raise ValueError("stress grid exceeds the 2000 run / 5000000 interval resource limit")
        for load in self.loads_Nm:
            if not math.isfinite(required_voltage(load, self.reference_rad_s)):
                raise ValueError("required voltage is outside the finite range")

    @property
    def expected_runs(self):
        return len(self.loads_Nm) * len(self.delays_s) * 2

    def scenario(self, load, delay):
        return Scenario(name="load_delay_grid", dt_s=self.dt_s, duration_s=self.duration_s,
                        reference=StepSignal(((0.0, 0.0), (0.5, self.reference_rad_s))),
                        load=StepSignal(((0.0, 0.0), (self.event_s, load))), measurement_delay_s=delay,
                        evaluation_start_s=self.event_s, recovery_start_s=self.event_s)


def required_voltage(load_Nm, reference_rad_s):
    p = DCMotor()
    damping = p.friction_Nm_s + p.torque_Nm_A * p.back_emf_V_s / p.resistance_ohm
    return (damping * reference_rad_s + load_Nm) * p.resistance_ohm / p.torque_Nm_A


def classify(metrics, feasible):
    if metrics["status"] != "completed":
        return "execution_or_metric_failure"
    if not feasible:
        return "steady_reference_infeasible"
    return "recovered" if metrics["recovery_status"] == "recovered_in_observation_window" else "not_recovered_in_window"


def cases(plan: StressPlan):
    for di, delay in enumerate(plan.delays_s):
        for label, anti in (("pid", False), ("pid_antiwindup", True)):
            baseline = None
            for li, load in enumerate(plan.loads_Nm):
                scenario = plan.scenario(load, delay)
                run = simulate(DCMotor(), PID(kp=plan.kp, ki=plan.ki, kd=plan.kd, anti_windup=anti), scenario)
                metrics = evaluate(run)
                if li == 0:
                    baseline = run
                incremental, pair_status, pair_matches = None, "paired_run_incomplete", None
                if metrics["status"] == "completed" and evaluate(baseline)["status"] == "completed":
                    pair_matches = len(run.rows) == len(baseline.rows) and all(
                        a["time_s"] == b["time_s"] and a["true_output_rad_s"] == b["true_output_rad_s"]
                        for a, b in zip(run.rows, baseline.rows) if a["time_s"] <= plan.event_s + 1e-12)
                    if not pair_matches:
                        raise RuntimeError("paired runs differ before the load event")
                    value = sum(abs(a["true_output_rad_s"] - b["true_output_rad_s"]) * a["interval_s"]
                                for a, b in zip(run.rows, baseline.rows) if a["time_s"] >= plan.event_s - 1e-12 and a["transition_completed"])
                    incremental = value if math.isfinite(value) else None
                    pair_status = "available" if math.isfinite(value) else "nonfinite"
                before = [r for r in run.rows if plan.event_s - scenario.recovery_dwell_s - 1e-12 <= r["time_s"] <= plan.event_s + 1e-12]
                expected = round(scenario.recovery_dwell_s / plan.dt_s) + 1
                observed = len(before) == expected and all(r["true_output_rad_s"] is not None for r in before)
                settled = all(abs(r["reference_rad_s"] - r["true_output_rad_s"]) <= scenario.recovery_band for r in before) if observed else None
                voltage = required_voltage(load, plan.reference_rad_s)
                feasible = abs(voltage) <= scenario.voltage_limit + 1e-12
                case_id = f"{label}__d{di:02d}_l{li:02d}"
                record = {"case_id": case_id, "controller_name": label, "load_Nm": load, "delay_s": delay,
                          "scenario": asdict(scenario), "plant": run.plant, "controller": run.controller,
                          "metrics": metrics, "classification": classify(metrics, feasible),
                          "steady_reference_feasible": feasible, "steady_required_voltage_V": voltage,
                          "pre_event_settled": settled, "pre_event_pair_matches": pair_matches,
                          "incremental_load_iae_rad": incremental, "incremental_status": pair_status,
                          "baseline_case_id": f"{label}__d{di:02d}_l00", "failure": run.failure,
                          "trace_file": case_id + ".csv", "record_file": case_id + ".json",
                          "trace_sha256": hashlib.sha256(json.dumps(run.rows, allow_nan=False).encode("utf8")).hexdigest()}
                yield record, run


def summarize(records):
    return [{"controller_name": label, "sampled_points": sum(r["controller_name"] == label for r in records),
             **{key: sum(r["controller_name"] == label and r["classification"] == key for r in records) for key in CLASSIFICATIONS},
             "pre_event_not_settled": sum(r["controller_name"] == label and r["pre_event_settled"] is False for r in records),
             "pre_event_unknown": sum(r["controller_name"] == label and r["pre_event_settled"] is None for r in records)}
            for label in ("pid", "pid_antiwindup")]


def execute_grid(output: Path, plan: StressPlan | None = None, *, plots=False):
    plan = plan or StressPlan()
    if plots:
        import matplotlib
    output.mkdir(parents=True, exist_ok=False)
    records, failed = [], 0
    try:
        write_json(output / "status.json", batch_status("in_progress", plan.expected_runs, 0, 0))
        write_json(output / "plan.json", {"feature": "load_measurement_delay_grid_development", "design": asdict(plan),
                   "expected_runs": plan.expected_runs, "delay_kind": "measurement_only", "controller_retuning": False,
                   "evidence": "synthetic_assumption", "probability_distribution": None,
                   "zero_load_controls_are_included_in_run_count": True,
                   "steady_positive_load_limit_Nm": (12 - required_voltage(0, plan.reference_rad_s)) * 0.1})
        for record, run in cases(plan):
            write_csv(output / record["trace_file"], run.rows)
            write_json(output / record["record_file"], record)
            records.append(record)
            failed += record["classification"] == "execution_or_metric_failure"
            write_json(output / "status.json", batch_status("in_progress", plan.expected_runs, len(records), failed))
        groups = summarize(records)
        write_csv(output / "summary.csv", [{k: v for k, v in r.items() if k not in ("scenario", "plant", "controller", "metrics", "failure")} | r["metrics"] for r in records])
        write_json(output / "manifest.json", {"project_version": __version__, "schema_version": "stress-grid-1.0",
                   "status_authority": "status.json", "feature": "load_measurement_delay_grid_development", "python": sys.version,
                   "evidence": "synthetic_assumption", "hardware_validated": False, "plan": asdict(plan),
                   "source_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))},
                   "groups": groups, "cases": records})
        figures = []
        if plots:
            from .stress_grid_plots import render
            figures = render(output, records, plan)
        titles = ("controller_name", "sampled_points", *CLASSIFICATIONS, "pre_event_not_settled", "pre_event_unknown")
        table = "<table><tr>" + "".join(f"<th>{key}</th>" for key in titles) + "</tr>"
        table += "".join("<tr>" + "".join(f"<td>{html.escape(str(group[key]))}</td>" for key in titles) + "</tr>" for group in groups) + "</table>"
        images = "".join(f'<section><h2>{html.escape(title)}</h2><a href="{name}.svg"><img src="{name}.png" alt="{html.escape(title)}"></a></section>' for name, title in figures)
        report = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                  '<title>ControlStressLab 扰动与延迟扫描</title><style>body{font:16px system-ui;max-width:1120px;margin:32px auto;padding:0 20px;color:#172033}'
                  'table{border-collapse:collapse;display:block;overflow:auto}td,th{border:1px solid #ddd;padding:8px}img{width:100%;height:auto}.note{background:#fff4d5;padding:16px}</style>'
                  '<h1>负载强度 × 测量延迟</h1><p class="note">合成网格，固定电机参数及PID增益，未经硬件验证。每次重新创建并复位；没有随机重复或概率权重。</p>'
                  f'<p>记录{len(records)}次，运行/指标失败{failed}次。评价区间[{plan.event_s},{plan.duration_s}) s。延迟仅作用于测量，负载阶跃作用于对象。</p>'
                  '<p>原始跟踪误差、同延迟零负载对照的输出增量积分分别解释。事件前未安定单独标记，负载幅值0的增量指标为0。</p>'
                  '<p>分类：恢复 / 观察窗内未恢复 / 精确稳态参考不可达 / 执行或指标失败。不可达不是不稳定，未恢复不是稳定性定理。'
                  '标称60 rad/s和±12 V下精确稳态负载上限为0.54 N m；恢复误差带与这一精确可达性条件不同。</p>'
                  '<p>热力图格子仅代表采样点，不保证格间表现。不给出单一精确临界延迟，不将采样点比例当成现实失效概率。</p>'
                  '<p><a href="plan.json">实验计划</a> · <a href="summary.csv">逐次指标</a> · <a href="manifest.json">配置及逐次文件索引</a> · <a href="status.json">权威完成状态</a></p>'
                  + table + images + '</html>')
        (output / "report.html").write_text(report, encoding="utf8", newline="\n")
        final = batch_status("completed_with_failures" if failed else "completed", plan.expected_runs, len(records), failed, complete=True)
        checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
        checksums["status.json"] = hashlib.sha256(json.dumps(final, indent=2, allow_nan=False).encode("utf8")).hexdigest()
        write_json(output / "checksums.json", checksums)
        write_json(output / "status.json", final)
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        try:
            write_json(output / "status.json", batch_status("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "aborted",
                       plan.expected_runs, len(records), failed, error=exc))
        except OSError:
            print("Unable to update stress-grid status; artifacts may be incomplete.", file=sys.stderr)
        raise
    return output / "report.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/stress-grid"))
    parser.add_argument("--loads", default=",".join(map(str, LOADS)), help="comma-separated N m, start with 0")
    parser.add_argument("--delays", default=",".join(map(str, DELAYS)), help="comma-separated seconds, start with 0")
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    try:
        plan = StressPlan(tuple(map(float, args.loads.split(","))), tuple(map(float, args.delays.split(","))))
        report = execute_grid(args.output, plan, plots=args.plots)
    except (ValueError, FileExistsError, ImportError) as exc:
        parser.error(str(exc))
    status = json.loads((args.output / "status.json").read_text(encoding="utf8"))
    print(f"Load-delay grid recorded: {report.resolve()} ({status['written_runs']} runs; {status['failed_runs']} execution/metric failures)")
    if status["failed_runs"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
