"""Run the predeclared, independently implemented SciPy comparison suite."""

import argparse
from dataclasses import asdict
import hashlib
import html
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from controlstresslab import DCMotor, FirstOrder, PID, simulate
from controlstresslab.metrics import evaluate
from controlstresslab.simulation import Scenario, StepSignal

CHANNELS = {"time": "time_s", "output": "true_output_rad_s", "measurement": "measurement_rad_s",
            "command": "command_V", "applied": "applied_V"}
TOLERANCES = {"trajectory_atol": 1e-8, "trajectory_rtol": 1e-9, "iae_atol": 1e-6, "iae_rtol": 1e-9}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite():
    cases = []

    def add(name, model, path, scenario, controller=None, **plant_changes):
        plant = model(**plant_changes)
        config = {k: v for k, v in asdict(plant).items() if k != "output"}
        cases.append({"id": name, "model": model.__name__, "path": path, "plant": config,
                      "controller": asdict(controller or PID()), "dt_s": scenario.dt_s,
                      "intervals": round(scenario.duration_s/scenario.dt_s),
                      "reference": scenario.reference.points, "load": scenario.load.points,
                      "noise": scenario.noise_sequence(), "delay_s": scenario.measurement_delay_s,
                      "voltage_limit": scenario.voltage_limit, "scenario": asdict(scenario)})
        # No private dynamic state is part of the interchange contract.
        cases[-1]["controller"] = {k: v for k, v in cases[-1]["controller"].items() if not k.startswith("_")}
        return cases[-1]

    for model in (FirstOrder, DCMotor):
        for dt in (0.01, 0.02, 0.05):
            for variant in range(3):
                params = ({"gain": (1, 2, -0.5)[variant], "tau_s": (1, 0.3, 2)[variant]}
                          if model is FirstOrder else {"inertia_kg_m2": (0.01, 0.005, 0.02)[variant],
                              "friction_Nm_s": (0.001, 0.002, 0.0005)[variant]})
                s = Scenario(dt_s=dt, duration_s=4, load=StepSignal(((0, 0.02), (1, 0.15), (2, -0.05))))
                c = add(f"open_{model.__name__}_{dt}_{variant}", model, "open_loop", s,
                        initial_output=(0, 3, -2)[variant], **params)
                c["input"] = [2.0 if k < round(1/dt) else (-1.0 if k < round(2/dt) else 4.0)
                              for k in range(c["intervals"] + 1)]
            s = Scenario(dt_s=dt, duration_s=6, reference=StepSignal(((0, 0), (0.5, 1))),
                         load=StepSignal(((0, 0), (3, 0.005))), recovery_start_s=3)
            add(f"linear_{model.__name__}_{dt}", model, "linear_pi", s)
    for aw in (False, True):
        for name in ("nominal", "load", "noise", "delay", "saturation_release"):
            event = name in ("load", "saturation_release")
            s = Scenario(name=name, load=StepSignal(((0, 0), (4, 0.15))) if name == "load" else StepSignal(),
                         reference=StepSignal(((0, 0), (0.5, 140), (4, 60))) if name == "saturation_release" else StepSignal(((0, 0), (0.5, 60))),
                         noise_std=0.6 if name == "noise" else 0,
                         measurement_delay_s=0.1 if name == "delay" else 0,
                         evaluation_start_s=4 if event else 0.5, recovery_start_s=4 if event else 0.5)
            add(f"closed_{name}_aw{int(aw)}", DCMotor, "ode_closed_loop", s, PID(anti_windup=aw))
        for load, delay in ((0.15, 0.3), (0.15, 0.35), (0.15, 0.5), (0.55, 0), (0.6, 0), (0.6, 0.5)):
            s = Scenario(name="stress_representative", duration_s=20, load=StepSignal(((0, 0), (8, load))),
                         measurement_delay_s=delay, evaluation_start_s=8, recovery_start_s=8)
            add(f"stress_{load}_{delay}_aw{int(aw)}", DCMotor, "ode_closed_loop", s, PID(anti_windup=aw))
        for filt in (0, 0.03):
            s = Scenario(name="measurement_derivative", dt_s=0.02, noise_std=0.2,
                         measurement_delay_s=0.1, load=StepSignal(((0, 0), (4, 0.15))), recovery_start_s=4)
            add(f"derivative_filter{filt}_aw{int(aw)}", DCMotor, "ode_closed_loop", s,
                PID(kd=0.02, anti_windup=aw, derivative_filter_s=filt))
    for j in (0.5, 2):
        for b in (0.5, 2):
            add(f"corner_J{j}_b{b}", DCMotor, "ode_closed_loop",
                Scenario(load=StepSignal(((0, 0), (4, 0.15))), recovery_start_s=4), PID(anti_windup=True),
                inertia_kg_m2=0.01*j, friction_Nm_s=0.001*b)
    return {"schema": "reference-suite-1.0", "tolerances": TOLERANCES, "cases": cases}


def scenario_of(case):
    data = dict(case["scenario"])
    for key in ("reference", "load"):
        data[key] = StepSignal(tuple(tuple(pair) for pair in data[key]["points"]))
    return Scenario(**data)


def product(case):
    plant = {"FirstOrder": FirstOrder, "DCMotor": DCMotor}[case["model"]](**case["plant"])
    if case["path"] == "open_loop":
        s = scenario_of(case)
        rows = []
        for k in range(case["intervals"] + 1):
            t = k * s.dt_s
            rows.append({"time": t, "output": plant.output,
                         "command": case["input"][k] if k < case["intervals"] else None})
            if k < case["intervals"]:
                plant.advance(case["input"][k], s.load.at(t), s.dt_s)
        return {"channels": {name: [r[name] for r in rows] for name in ("time", "output", "command")}, "metrics": None}
    run = simulate(plant, PID(**case["controller"]), scenario_of(case), fail_fast=True)
    if run.status != "completed":
        raise RuntimeError(f"{case['id']}: {run.status}")
    channels = {name: [r[field] for r in run.rows] for name, field in CHANNELS.items()}
    if case["path"] == "linear_pi" and any(abs(u) >= case["voltage_limit"] for u in channels["command"][:-1]):
        raise ValueError("linear PI product unexpectedly reaches saturation")
    return {"channels": channels, "metrics": evaluate(run)}


def compare_channel(actual, expected, *, exact=False):
    if len(actual) != len(expected) or not actual:
        return {"passed": False, "reason": "length_mismatch_or_empty", "max_abs_error": None}
    errors, ratios, passed = [], [], True
    for a, b in zip(actual, expected):
        if a is None or b is None:
            passed = passed and a is None and b is None
            continue
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (a, b)):
            return {"passed": False, "reason": "nonfinite_or_invalid", "max_abs_error": None}
        error = abs(a - b)
        bound = 0 if exact else TOLERANCES["trajectory_atol"] + TOLERANCES["trajectory_rtol"] * abs(b)
        passed = passed and error <= bound
        errors.append(error)
        if not exact:
            ratios.append(error / bound)
    return {"passed": bool(passed), "max_abs_error": max(errors, default=0),
            "max_tolerance_fraction": max(ratios, default=0)}


def reference_metrics(case, channels):
    # Standalone reduction: reconstruct left-endpoint reference and final in-band tail.
    s = case["scenario"]
    n, dt = case["intervals"], case["dt_s"]
    refs = [0.0] * (n + 1)
    for event, value in case["reference"]:
        refs[round(event/dt):] = [value] * (n + 1 - round(event/dt))
    errors = [abs(r-y) for r, y in zip(refs, channels["output"])]
    iae = math.fsum(e*dt for e in errors[round(s["evaluation_start_s"]/dt):n])
    anchor = round(s["recovery_start_s"]/dt)
    last = max((k for k in range(anchor, n+1) if errors[k] > s["recovery_band"]), default=anchor-1)
    start = last + 1
    recovered = start <= n and (n-start)*dt >= s["recovery_dwell_s"] - 1e-12
    return {"iae_rad": iae, "recovery_status": "recovered_in_observation_window" if recovered else "not_recovered_in_observation_window",
            "recovery_time_s": max(0.0, start*dt - s["recovery_start_s"]) if recovered else None}


def compare_case(case, actual, expected):
    results = {key: compare_channel(actual["channels"][key], expected.get(key, []), exact=key == "time")
               for key in actual["channels"]}
    for key in ("command", "applied"):
        if key in actual["channels"]:
            valid_terminal = actual["channels"][key][-1] is None and expected.get(key, [0])[-1] is None
            results[key]["passed"] = results[key]["passed"] and valid_terminal
    for key, check in results.items():
        a, b = actual["channels"][key], expected.get(key, [])
        check["passed"] = check["passed"] and len(a) == len(b) == case["intervals"] + 1
        # Missing physical samples cannot count as matching merely because both are null.
        end = -1 if key in ("command", "applied") else len(a)
        check["passed"] = check["passed"] and all(v is not None for v in a[:end] + b[:end])
    metrics = {}
    if actual["metrics"] is not None:
        values = expected.get("output", [])
        if len(values) != case["intervals"] + 1 or any(v is None or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            return {"id": case["id"], "path": case["path"], "channels": results,
                    "metrics": {"passed": False, "reason": "output_comparison_failed"}, "passed": False}
        independent = reference_metrics(case, expected)
        a, b = actual["metrics"]["iae_rad"], independent["iae_rad"]
        metrics = {"product": {k: actual["metrics"][k] for k in independent}, "reference": independent,
                   "iae_abs_error": abs(a-b),
                   "passed": abs(a-b) <= TOLERANCES["iae_atol"] + TOLERANCES["iae_rtol"]*abs(b)
                       and all(actual["metrics"][k] == independent[k] for k in ("recovery_status", "recovery_time_s"))}
    return {"id": case["id"], "path": case["path"], "channels": results, "metrics": metrics,
            "passed": all(x["passed"] for x in results.values()) and metrics.get("passed", True)}


def run(output, reference_python, plots=False):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "status.json", {"state": "in_progress", "artifacts_complete": False})
    try:
        inputs = suite()
        write_json(output / "suite.json", inputs)
        products = {c["id"]: product(c) for c in inputs["cases"]}
        write_json(output / "product.json", {"python": platform.python_version(), "cases": products})
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        result = subprocess.run([str(reference_python), "-I", str(ROOT / "scripts/scipy_reference.py"),
                                 "--input", str(output / "suite.json"), "--output", str(output / "reference.json")],
                                env=env, capture_output=True, text=True)
        (output / "reference_process.log").write_text(result.stdout + result.stderr, encoding="utf8", newline="\n")
        result.check_returncode()
        oracle = json.loads((output / "reference.json").read_text(encoding="utf8"))
        if set(products) != set(oracle["cases"]):
            raise ValueError("reference case IDs differ")
        comparisons = [compare_case(c, products[c["id"]], oracle["cases"][c["id"]]) for c in inputs["cases"]]
        failures = sum(not c["passed"] for c in comparisons)
        write_json(output / "comparison.json", {"tolerances": TOLERANCES, "cases": comparisons, "failed": failures})
        source_hashes = {p.name: digest(p) for p in sorted((ROOT / "src/controlstresslab").glob("*.py"))}
        reference_sources = {}
        for name in ("scripts/reference_checks.py", "scripts/scipy_reference.py", "scripts/reference_plots.py",
                     "docs/REFERENCE_COMPARISON_DESIGN.md"):
            p = ROOT / name
            reference_sources[name] = digest(p)
            target = output / "reference_source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
        manifest = {"schema": "reference-comparison-1.0", "feature": "independent_numerical_comparison_development",
                    "evidence": "synthetic_assumption", "reference_environment": oracle["environment"],
                    "product_python": platform.python_version(), "methods": oracle["methods"],
                    "case_count": len(comparisons), "failed": failures, "source_files_sha256": source_hashes,
                    "reference_sources_sha256": reference_sources}
        write_json(output / "manifest.json", manifest)
        if plots:
            from reference_plots import build
            build(output, inputs, products, oracle["cases"], comparisons)
        figures = "".join(f'<a href="figures/{p.name}"><img src="figures/{p.name}" style="max-width:100%"></a>'
                          for p in sorted((output / "figures").glob("*.png"))) if plots else ""
        def display_error(c):
            v = c["channels"]["output"]["max_abs_error"]
            return "invalid" if v is None else f"{v:.3e}"
        rows = "".join(f"<tr><td>{html.escape(c['id'])}</td><td>{c['path']}</td><td>{'PASS' if c['passed'] else 'FAIL'}</td>"
                       f"<td>{display_error(c)}</td></tr>" for c in comparisons)
        report = f'''<!doctype html><meta charset="utf-8"><title>独立工具数值对照</title>
<style>body{{font:16px sans-serif;max-width:1200px;margin:32px auto;padding:16px;line-height:1.6}}td,th{{border:1px solid #bbb;padding:5px}}table{{border-collapse:collapse}}</style>
<h1>独立工具数值对照</h1><p>{len(comparisons)}个预定对照，失败{failures}个。SciPy {oracle['environment']['scipy']}，参考Python {oracle['environment']['python']}，产品Python {platform.python_version()}。</p>
<p>矩阵指数/ZOH与DOP853两种数值路径。参考脚本不导入产品、不读取产品轨迹；同一开发者实现，并非第三方审计。
全部为合成模型；通过只支持数值实现一致，不证明模型参数真实、硬件可用或闭环普遍稳定。</p>
<p>逐采样点容差：1e-8 + 1e-9×|参考值|；IAE容差1e-6 + 1e-9×|参考值|；恢复状态及网格时间完全一致。
这些配置不是独立随机重复，选点对照不等于复算全部既有网格。</p>
<p><a href="comparison.json">逐项判据</a> · <a href="suite.json">全部输入</a> · <a href="product.json">产品原始轨迹</a> · <a href="reference.json">参考原始轨迹</a> · <a href="manifest.json">环境与源码指纹</a></p>
{figures}<table><tr><th>配置</th><th>路径</th><th>判定</th><th>最大输出绝对差</th></tr>{rows}</table>'''
        (output / "report.html").write_text(report, encoding="utf8", newline="\n")
        final = {"state": "failed" if failures else "completed", "expected_runs": len(comparisons),
                 "written_runs": len(comparisons), "failed_runs": failures, "artifacts_complete": True}
        final_bytes = (json.dumps(final, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf8")
        hashes = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob("*"))
                  if p.is_file() and p.name != "status.json"}
        hashes["status.json"] = hashlib.sha256(final_bytes).hexdigest()
        write_json(output / "checksums.json", hashes)
        (output / "status.json").write_bytes(final_bytes)
        print(f"Compared {len(comparisons)} cases, failures={failures}: {output / 'report.html'}")
        return 1 if failures else 0
    except BaseException as exc:
        write_json(output / "status.json", {"state": "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "export_or_reference_failure",
                                          "artifacts_complete": False, "error_type": type(exc).__name__, "message": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.reference_python, args.plots))
