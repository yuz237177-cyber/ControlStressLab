"""Paired demo suite and dependency-free HTML/CSV/JSON output."""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import csv
import hashlib
import html
import json
from pathlib import Path
import platform
import sys

from . import __version__
from .controllers import PID
from .metrics import evaluate
from .models import DCMotor
from .reporting import charts
from .simulation import Scenario, StepSignal, simulate


def demo_scenarios(dt: float, seed: int) -> list[Scenario]:
    base = Scenario(dt_s=dt, seed=seed)
    return [base,
            replace(base, name="load_step", load=StepSignal(((0.0, 0.0), (4.0, 0.15))), recovery_start_s=4.0),
            replace(base, name="measurement_noise", noise_std=1.0),
            replace(base, name="measurement_delay", measurement_delay_s=0.1),
            replace(base, name="saturation_release",
                    reference=StepSignal(((0.0, 0.0), (0.5, 140.0), (4.0, 60.0))), recovery_start_s=4.0)]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict) -> None:
    from .experiment import atomic_json
    atomic_json(path,value)


def batch_status(state: str, expected: int, written: int, failed: int, *, complete: bool = False, error: BaseException | None = None) -> dict:
    """Stable status schema. Only the final write commits a complete artifact set."""
    return {"schema_version": "1.0", "state": state, "expected_runs": expected,
            "written_runs": written, "failed_runs": failed, "artifacts_complete": complete,
            "error_type": type(error).__name__ if error else None,
            "message": str(error) if error else None}


def execute_demo(output: Path, dt: float = 0.01, seeds: tuple[int, ...] = (42,), *, continue_on_failure: bool = False) -> Path:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be nonempty and unique")
    suites = [(seed, demo_scenarios(dt, seed)) for seed in seeds]
    # Refuse overwrite so runs retain their original configuration and provenance.
    output.mkdir(parents=True, exist_ok=False)
    summary, cards, records = [], [], []
    tasks = [(seed, scenario, label, anti) for seed, scenarios in suites for scenario in scenarios
             for label, anti in (("pid", False), ("pid_antiwindup", True))]
    failed = 0
    metadata = None
    try:
        write_json(output / "status.json", batch_status("in_progress", len(tasks), 0, 0))
        for seed, scenario, label, anti in tasks:
            run = simulate(DCMotor(), PID(anti_windup=anti), scenario)
            metrics = evaluate(run)
            stem = f"{scenario.name}__{label}__seed{seed}"
            write_csv(output / f"{stem}.csv", run.rows)
            record = {"scenario": asdict(scenario), "controller_name": label, "controller": run.controller,
                      "plant": run.plant, "metrics": metrics, "trace_file": f"{stem}.csv",
                      "failure": run.failure, "diagnostics": run.diagnostics}
            write_json(output / f"{stem}.json", record)
            summary.append({"scenario": scenario.name, "controller": label, "seed": seed, **metrics})
            records.append(record)
            failed += metrics["status"] != "completed"
            rendered = html.escape(json.dumps(metrics, indent=2, allow_nan=False))
            notes = " · ".join(html.escape(note) for note in run.diagnostics)
            cards.append(f'<section><h2>{html.escape(stem)}</h2><p>{notes}</p>'
                         f'{charts(run.rows, scenario.recovery_start_s)}<pre>{rendered}</pre>'
                         f'<a href="{stem}.csv">轨迹 CSV</a> · <a href="{stem}.json">配置、状态与诊断</a></section>')
            write_json(output / "status.json", batch_status("in_progress", len(tasks), len(records), failed))
            if failed and not continue_on_failure:
                break
        batch_state = "completed" if not failed else "completed_with_failures" if continue_on_failure else "stopped_on_failure"
        write_csv(output / "summary.csv", summary)
        metadata = {"project_version": __version__, "schema_version": "1.2", "trace_schema_version": "1.1",
                "status_authority": "status.json", "python": sys.version, "platform": platform.platform(),
                "created_utc": datetime.now(timezone.utc).isoformat(), "dt_s": dt, "seeds": list(seeds),
                "batch_status": batch_state, "expected_runs": len(tasks), "written_runs": len(records),
                "failed_runs": failed, "continue_on_failure": continue_on_failure,
                "evidence": "synthetic_assumption", "hardware_validated": False,
                "source_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted(Path(__file__).parent.glob("*.py"))},
                "recovery_definition": "final uninterrupted in-band segment lasting at least the configured dwell, within the observation window",
                "runs": records}
        document = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                '<title>ControlStressLab report</title><style>body{font:16px system-ui;max-width:980px;margin:36px auto;padding:0 20px;color:#172033}'
                'section{border-top:1px solid #ddd;padding:20px 0}svg{width:100%;max-width:780px;font:11px system-ui}pre{background:#f3f5f8;padding:16px;overflow:auto}'
                '.evidence{background:#fff4d5;padding:18px}.note{font-size:13px;color:#475569}a{color:#1d4ed8}</style>'
                '<h1>ControlStressLab · motor demo</h1><p class="evidence"><strong>SYNTHETIC SIMULATION — NOT HARDWARE VALIDATED.</strong> '
                'Illustrative model parameters and disturbance assumptions. Results apply to these configurations only; '
                'they do not establish universal stability or industrial suitability.</p>'
                '<p>Identical scenario/noise samples are paired across controllers. Metrics use true plant output, not noisy measurements. '
                'A completed run is not a stability proof. No aggregate ranking is computed.</p>'
                f'<p>批次状态：{batch_state} · 已记录 {len(records)}/{len(tasks)} 次 · 失败 {failed} 次。</p>'
                '<p>全程指标保留起步瞬态；pre/post 指标按 recovery_start_s 锚点拆分，空窗口为 null。'
                '恢复时间依据仿真真实状态，不能直接照搬为实测判据。输入总变差不是能耗；跨采样周期或噪声带宽比较时应先统一条件。</p>'
                '<p>端点和未发出动作的状态行输入为空；失败时可能已发出动作而推进未完成。只有 transition_completed=true 的行覆盖 interval_s。'
                '输入图仅显示 action_taken=true 的动作，不包含虚构的终点关断。四个确定性场景更换种子不会增加独立证据。</p>'
                '<p><a href="summary.csv">Summary CSV</a> · <a href="manifest.json">Experiment manifest</a> · '
                '<a href="status.json">权威批次状态</a>。仅当 artifacts_complete=true 且校验值通过时，产物集才完整。</p>'
                + "".join(cards) + '</html>')
        (output / "report.html").write_text(document, encoding="utf-8")
        write_json(output / "manifest.json", metadata)
        final_status = batch_status(batch_state, len(tasks), len(records), failed, complete=True)
        checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
        # Hash the planned final status bytes, then commit that status only after all artifacts exist.
        checksums["status.json"] = hashlib.sha256(json.dumps(final_status, indent=2, allow_nan=False).encode("utf-8")).hexdigest()
        write_json(output / "checksums.json", checksums)
        write_json(output / "status.json", final_status)
    except (Exception, KeyboardInterrupt, SystemExit) as exc:
        state = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "aborted"
        try:
            write_json(output / "status.json", batch_status(state, len(tasks), len(records), failed, error=exc))
        except OSError:
            print("Unable to update status.json; output may be incomplete.", file=sys.stderr)
        if metadata is not None and (output / "manifest.json").exists():
            try:
                metadata["batch_status"] = state
                write_json(output / "manifest.json", metadata)
            except OSError:
                print("Unable to update manifest.json; use status.json and verify checksums.", file=sys.stderr)
        raise
    return output / "report.html"


def main() -> None:
    parser = argparse.ArgumentParser(description="ControlStressLab synthetic motor stress-test demo")
    parser.add_argument("--output", type=Path, default=Path("outputs/demo"))
    parser.add_argument("--dt", type=float, default=0.01, help="controller sample period in seconds")
    parser.add_argument("--seeds", default="42", help="comma-separated seeds; e.g. 11,22,33 (no statistical sample-size guarantee)")
    parser.add_argument("--continue-on-failure", action="store_true", help="record failed runs and continue the remaining suite")
    args = parser.parse_args()
    try:
        seeds = tuple(int(part) for part in args.seeds.split(","))
        if not seeds or len(set(seeds)) != len(seeds):
            raise ValueError("seeds must be nonempty and unique")
        # Validate before creating any output directory.
        demo_scenarios(args.dt, seeds[0])
        report = execute_demo(args.output, args.dt, seeds, continue_on_failure=args.continue_on_failure)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    failed = json.loads((args.output / "manifest.json").read_text(encoding="utf8"))["failed_runs"]
    print(f"Synthetic demo {'recorded with ' + str(failed) + ' failed runs' if failed else 'complete'}: {report.resolve()}")
    print("Evidence: synthetic_assumption; hardware_validated: false")
    if failed:
        parser.exit(1, "One or more runs failed; see the report and diagnostics.\n")


if __name__ == "__main__":
    main()
