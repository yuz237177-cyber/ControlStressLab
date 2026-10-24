"""Paired coverage suite across signals, controller families and physical domains."""

import argparse
from dataclasses import asdict
import hashlib
import html
import json
from pathlib import Path
import platform

from .cli import batch_status, write_csv, write_json
from .controllers import PID
from .extended_controllers import LinearADRC, TwoDOFPID
from .extended_models import InductiveDCMotor, MassSpringDamper
from .metrics import evaluate
from .models import DCMotor, FirstOrder
from .signals import waveform
from .simulation import Scenario, simulate

MODEL_NAMES = ("first_order", "reduced_motor", "inductive_motor", "mass_spring_damper")
CONTROLLER_NAMES = ("PI", "PID_aw", "TwoDOF_PID", "LADRC")
SCENARIO_NAMES = tuple("reference_"+k for k in ("step", "ramp", "sine", "triangle", "chirp", "multistep")) + tuple(
    "disturbance_"+k for k in ("step", "pulse", "sine", "square", "chirp", "prbs")) + ("combined_sine_prbs", "measurement_noise_delay")
COLUMN_MAP = {"time_s": "time_s", "reference": "reference_rad_s", "output": "true_output_rad_s",
              "measurement": "measurement_rad_s", "requested_input": "command_V", "applied_input": "applied_V",
              "disturbance": "load_Nm", "interval_s": "interval_s", "action_taken": "action_taken", "transition_completed": "transition_completed"}


def model_spec(name):
    if name not in MODEL_NAMES:
        raise ValueError("unknown model")
    if name == "first_order":
        return dict(factory=FirstOrder, units=dict(output="unit", input="unit", disturbance="unit"),
                    scale=1.0, limit=3.0, disturbance=0.2, gains=(1.5, 1, 0.1), adrc=(1, 1, 2.5, 10))
    if name in ("reduced_motor", "inductive_motor"):
        return dict(factory=DCMotor if name == "reduced_motor" else InductiveDCMotor,
                    units=dict(output="rad/s", input="V", disturbance="N m"), scale=60.0, limit=12.0,
                    disturbance=0.15, gains=(0.25, 0.8, 0.015 if name == "reduced_motor" else 0.03),
                    adrc=(1, 10, 3, 12) if name == "reduced_motor" else (2, 50, 2, 10))
    return dict(factory=MassSpringDamper, units=dict(output="m", input="N", disturbance="N"),
                scale=0.5, limit=5.0, disturbance=0.5, gains=(6, 3, 3), adrc=(2, 1, 2.5, 10))


def controllers(spec):
    kp, ki, kd = spec["gains"]
    degree, b0, wc, wo = spec["adrc"]
    return (("PI", PID(kp, ki, 0)), ("PID_aw", PID(kp, ki, kd, anti_windup=True)),
            ("TwoDOF_PID", TwoDOFPID(kp=kp, ki=ki, kd=kd, anti_windup=True, beta=0.6)),
            ("LADRC", LinearADRC(degree, b0, wc, wo)))


def scenario(name, spec):
    if name not in SCENARIO_NAMES:
        raise ValueError("unknown coverage scenario")
    scale = spec["scale"]
    ref = waveform("step", amplitude=scale)
    load = waveform("constant", amplitude=0)
    anchor, mode = 0.5, "settling"
    if name.startswith("reference_"):
        kind = name.removeprefix("reference_")
        periodic = kind in ("sine", "triangle", "chirp")
        ref = waveform(kind, amplitude=(0.3 if periodic else 1)*scale, offset=0.7*scale if periodic else 0)
        anchor = 4.5 if kind == "ramp" else (6.5 if kind == "multistep" else 0.5)
        if periodic: mode = "tracking_only"
    elif name.startswith("disturbance_"):
        kind = name.removeprefix("disturbance_")
        load = waveform(kind, amplitude=spec["disturbance"], start_s=6.0)
        anchor = 7.0 if kind == "pulse" else 6.0
        if kind not in ("step", "pulse"): mode = "tracking_only"
    elif name == "combined_sine_prbs":
        ref = waveform("sine", offset=0.7*scale, amplitude=0.3*scale)
        load = waveform("prbs", amplitude=spec["disturbance"], start_s=6.0)
        anchor, mode = 6.0, "tracking_only"
    return Scenario(name=name, duration_s=16, reference=ref, load=load,
                    voltage_limit=spec["limit"], output_bound=40*scale,
                    noise_std=0.01*scale if name == "measurement_noise_delay" else 0,
                    measurement_delay_s=0.05 if name == "measurement_noise_delay" else 0,
                    evaluation_start_s=0.5, recovery_start_s=anchor, recovery_mode=mode,
                    recovery_band=0.02*scale)


def neutral_metrics(run, spec):
    raw = evaluate(run)
    mapping = {"rmse": "rmse_rad_s", "iae": "iae_rad", "max_abs_error": "max_abs_error_rad_s",
               "input_total_variation": "input_total_variation_V", "saturation_fraction": "saturation_fraction",
               "recovery_time_s": "recovery_time_s", "recovery_status": "recovery_status"}
    result = {key: raw[value] for key, value in mapping.items()}
    result.update(status=raw["status"], reason=raw["reason"], metric_source="model_state")
    for key, source, denominator in (("normalized_rmse", "rmse", spec["scale"]),
        ("normalized_iae", "iae", spec["scale"]*(run.scenario.duration_s-run.scenario.evaluation_start_s)),
        ("normalized_input_variation", "input_total_variation", spec["limit"])):
        result[key] = None if result[source] is None else result[source]/denominator
    return result


def validate_selection(names, allowed, label):
    if not names or len(set(names)) != len(names) or any(n not in allowed for n in names):
        raise ValueError(f"invalid or repeated {label}")


def execute(output, model_names=MODEL_NAMES, scenario_names=SCENARIO_NAMES, *, plots=False):
    validate_selection(model_names, MODEL_NAMES, "models")
    validate_selection(scenario_names, SCENARIO_NAMES, "scenarios")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    expected = len(model_names)*len(scenario_names)*len(CONTROLLER_NAMES)
    written, failed, records = 0, 0, []
    write_json(output / "status.json", batch_status("in_progress", expected, 0, 0))
    try:
        (output / "inputs").mkdir()
        (output / "runs").mkdir()
        manifest = {"schema_version": "coverage-1.0", "trace_schema_version": "generic-1.0",
                    "feature": "waveforms_algorithms_models_development", "hardware_validated": False,
                    "python": platform.python_version(), "evidence": "synthetic_assumption", "expected_runs": expected,
                    "models": list(model_names), "scenarios": list(scenario_names), "controllers": list(CONTROLLER_NAMES),
                    "pairing": "same model + scenario => same signals, grid, limit, noise array; no per-case retuning",
                    "source_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))},
                    "column_map_from_legacy_core": COLUMN_MAP, "artifacts_complete": False}
        write_json(output / "manifest.json", manifest)
        for model_name in model_names:
            spec = model_spec(model_name)
            for scenario_name in scenario_names:
                s = scenario(scenario_name, spec)
                input_name = f"inputs/{model_name}__{scenario_name}.json"
                noise = s.noise_sequence()
                write_json(output / input_name, {"scenario": asdict(s), "noise": noise, "units": spec["units"],
                                               "reference_scale": spec["scale"], "input_limit": spec["limit"]})
                input_hash = hashlib.sha256((output / input_name).read_bytes()).hexdigest()
                for label, controller in controllers(spec):
                    case_id = f"{model_name}__{scenario_name}__{label}"
                    run = simulate(spec["factory"](), controller, s)
                    metrics = neutral_metrics(run, spec)
                    failed += metrics["status"] != "completed"
                    trace = f"runs/{case_id}.csv"
                    write_csv(output / trace, [{new: row[old] for new, old in COLUMN_MAP.items()} for row in run.rows])
                    record = {"case_id": case_id, "model_name": model_name, "scenario_name": scenario_name,
                              "controller_name": label, "plant": run.plant, "controller": run.controller,
                              "units": spec["units"], "reference_scale": spec["scale"], "input_limit": spec["limit"],
                              "scenario": asdict(s), "input_file": input_name, "input_sha256": input_hash,
                              "trace_file": trace, "trace_file_sha256": hashlib.sha256((output / trace).read_bytes()).hexdigest(),
                              "metrics": metrics, "failure": run.failure}
                    write_json(output / f"runs/{case_id}.json", record)
                    records.append(record)
                    written += 1
                    write_json(output / "status.json", batch_status("in_progress", expected, written, failed))
            print(f"Coverage model complete: {model_name}; written={written}/{expected}; failed={failed}", flush=True)
        fields = ("case_id", "model_name", "scenario_name", "controller_name", "status", "rmse", "iae", "normalized_rmse",
                  "normalized_iae", "input_total_variation", "normalized_input_variation", "saturation_fraction", "recovery_time_s", "recovery_status")
        write_csv(output / "summary.csv", [{key: r.get(key, r["metrics"].get(key)) for key in fields} for r in records])
        if plots:
            from .coverage_plots import build
            build(output, records)
        images = "".join(f'<a href="figures/{p.name}"><img src="figures/{p.name}" loading="lazy"></a>' for p in sorted((output / "figures").glob("*.png")))
        rows = "".join(f"<tr><td>{html.escape(r['case_id'])}</td><td>{r['metrics']['status']}</td>"
                       f"<td>{r['metrics']['normalized_iae']}</td><td>{r['metrics']['recovery_status']}</td>"
                       f"<td><a href='{r['trace_file']}'>CSV</a> · <a href='runs/{r['case_id']}.json'>配置</a></td></tr>" for r in records)
        units = "".join(f"<tr><td>{m}</td><td>{model_spec(m)['units']['output']}</td><td>{model_spec(m)['units']['input']}</td><td>{model_spec(m)['units']['disturbance']}</td></tr>" for m in model_names)
        (output / "report.html").write_text(f'''<!doctype html><meta charset="utf-8"><title>波形、控制器和对象覆盖</title>
<style>body{{font:16px sans-serif;line-height:1.6;max-width:1250px;margin:30px auto;padding:16px}}img{{max-width:100%}}table{{border-collapse:collapse;font-size:13px}}td,th{{padding:5px;border:1px solid #ccc}}</style>
<h1>波形、控制器和对象覆盖</h1><p>{expected}次配置，执行/指标失败{failed}次。合成教学模型，未经硬件验证。</p>
<p>同一对象/场景共用信号、采样、噪声与限幅。参数按对象固定，未按场景重新调参；各算法未统一优化，不能据此判定算法普遍优劣。</p>
<p>波形是预先采样并零阶保持的输入。持续变化参考/持续扰动使用tracking_only，恢复指标为不适用。</p>
<p>通用CSV列名与单位表一起读取；NIAE=IAE/(参考尺度×评价时长)，NRMSE=RMSE/尺度。失败指标为null，不计零分。</p>
<p>本轮完整窗口误差包含起步过程，不能把扰动场景的IAE直接解释为纯扰动效应；隔离扰动效应需要与同参考的无扰动轨迹配对分析。</p>
<p><a href="summary.csv">汇总CSV</a> · <a href="manifest.json">源码指纹与配置</a> · <a href="status.json">完整性状态</a></p>
<table><tr><th>对象</th><th>输出</th><th>输入</th><th>扰动</th></tr>{units}</table>{images}
<table><tr><th>配置</th><th>执行状态</th><th>NIAE</th><th>恢复判定</th><th>数据</th></tr>{rows}</table>''', encoding="utf8", newline="\n")
        manifest.update(written_runs=written, failed_runs=failed, artifacts_complete=True)
        write_json(output / "manifest.json", manifest)
        final = batch_status("completed_with_failures" if failed else "completed", expected, written, failed, complete=True)
        status_bytes = json.dumps(final, indent=2, allow_nan=False).encode("utf8")
        hashes = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob("*")) if p.is_file() and p.name != "status.json"}
        hashes["status.json"] = hashlib.sha256(status_bytes).hexdigest()
        write_json(output / "checksums.json", hashes)
        (output / "status.json").write_bytes(status_bytes)
        return output / "report.html", failed
    except BaseException as exc:
        try:
            write_json(output / "status.json", batch_status("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "export_failure", expected, written, failed, error=exc))
        except Exception:
            pass
        # A manifest never remains complete when the final artifact commit fails.
        if (output / "manifest.json").exists():
            manifest["artifacts_complete"] = False
            try:
                write_json(output / "manifest.json", manifest)
            except Exception:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", default=",".join(MODEL_NAMES))
    parser.add_argument("--scenarios", default=",".join(SCENARIO_NAMES))
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    report, failed = execute(args.output, tuple(args.models.split(",")), tuple(args.scenarios.split(",")), plots=args.plots)
    print(f"Coverage report: {report}; failures={failed}")
    if failed: parser.exit(1, "Failed runs retained; inspect report and failure records.\n")


if __name__ == "__main__":
    main()
