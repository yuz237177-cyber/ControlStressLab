"""Validated, paired desktop/CLI experiments; no GUI or plotting dependencies."""

import argparse
from copy import deepcopy
import csv
from dataclasses import asdict, fields
import hashlib
import html
import json
import math
from pathlib import Path
import platform
import uuid
import zipfile

from . import __version__
from .benchmark_design import CONTROLLERS, controller_for, spec_for
from .cli import batch_status, write_csv
from .coverage import COLUMN_MAP, controllers, neutral_metrics
from .extended_models import MassSpringDamper
from .models import FirstOrder
from .signals import waveform
from .simulation import Scenario, parameters, simulate

MODELS = {"first_order": FirstOrder, "second_order": MassSpringDamper}
KINDS = ("constant", "step", "ramp", "sine", "triangle", "chirp", "multistep", "pulse", "square", "prbs")


class Cancelled(KeyboardInterrupt):
    """Cooperative cancellation between complete runs; partial files are retained."""


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf8", newline="\n")
    temporary.replace(path)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def default_config(model="first_order"):
    spec = spec_for(model)
    signal = dict(kind="step", amplitude=spec["scale"], offset=0.0, start_s=0.5, frequency_hz=0.25,
                  stop_frequency_hz=0.8, ramp_duration_s=4.0, pulse_width_s=1.0, hold_s=0.5, seed=42)
    plant = MODELS[model]()
    return dict(schema="experiment-1.0", name="一阶惯性 · 阶跃抗扰" if model == "first_order" else "二阶振荡 · 正弦跟踪",
        model=model, plant={f.name: getattr(plant, f.name) for f in fields(plant) if f.init and f.name != "output"},
        controllers=[dict(name=n, parameters={k: v for k, v in parameters(c).items() if k not in ("type", "params_recorded")}) for n, c in controllers(spec)],
        selected_controllers=["PI", "PID_aw"], reference=signal,
        disturbance={**signal, "amplitude": spec["disturbance"], "start_s": 6.0},
        conditions=dict(dt_s=0.01, duration_s=12.0, input_limit=spec["limit"], output_bound=40*spec["scale"],
            noise_std=0.0, measurement_delay_s=0.0, seed=42, evaluation_start_s=0.5, recovery_start_s=6.0,
            recovery_band=0.02*spec["scale"], recovery_dwell_s=0.5, recovery_mode="auto", reference_scale=spec["scale"]))


def presets():
    a, b, c = default_config(), default_config("second_order"), default_config()
    b["reference"].update(kind="sine", amplitude=0.175, offset=0.325, frequency_hz=0.37)
    b["disturbance"].update(kind="constant", amplitude=0)
    b["selected_controllers"] = ["PID_aw", "LADRC"]
    c.update(name="LADRC · 噪声与延迟", selected_controllers=["PID_aw", "LADRC"])
    c["conditions"].update(noise_std=0.02, measurement_delay_s=0.07)
    return [a, b, c]


def keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(label+"字段与配置版本不匹配")


def finite_tree(value, label="配置"):
    if isinstance(value, dict):
        for key, v in value.items(): finite_tree(v, label+"."+key)
    elif isinstance(value, list):
        for v in value: finite_tree(v, label)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(label+"必须为有限数值")


def make_signal(value, conditions):
    # Unused timing parameters must not constrain unrelated waveform kinds.
    kw = dict(value)
    kind = kw.pop("kind")
    relevant = {"ramp_duration_s": ("ramp",), "pulse_width_s": ("pulse",), "hold_s": ("prbs",)}
    for key, allowed in relevant.items():
        if kind not in allowed: kw[key] = conditions["dt_s"]
    return waveform(kind, dt_s=conditions["dt_s"], duration_s=conditions["duration_s"], **kw)


def validate_config(value):
    finite_tree(value)
    keys(value, default_config(), "实验")
    config = deepcopy(value)
    if config["schema"] != "experiment-1.0" or not isinstance(config["model"], str) or config["model"] not in MODELS:
        raise ValueError("不支持的实验版本或对象")
    if not isinstance(config["name"], str) or not config["name"].strip() or len(config["name"]) > 120:
        raise ValueError("实验名称需为1～120个字符")
    defaults = default_config(config["model"])
    keys(config["plant"], defaults["plant"], "对象参数")
    keys(config["conditions"], defaults["conditions"], "实验条件")
    for label in ("reference", "disturbance"):
        signal = config[label]
        keys(signal, defaults[label], label)
        if signal["kind"] not in KINDS: raise ValueError("未知波形")
        if type(signal["seed"]) is not int or not 0 <= signal["seed"] < 2**32: raise ValueError("信号种子必须为非负整数")
        for k, v in signal.items():
            if k not in ("kind", "seed") and type(v) not in (int, float): raise ValueError("信号参数必须为实数")
    names = config["selected_controllers"]
    if not isinstance(names, list) or not names or any(n not in CONTROLLERS for n in names) or len(set(names)) != len(names):
        raise ValueError("至少选择一种控制器，且不能重复")
    definitions = config["controllers"]
    if not isinstance(definitions, list) or len(definitions) != 4: raise ValueError("需保留四种控制器的完整参数")
    if [x.get("name") for x in definitions if isinstance(x, dict)] != list(CONTROLLERS): raise ValueError("控制器定义或顺序无效")
    for definition, default in zip(definitions, defaults["controllers"]):
        keys(definition, default, "控制器")
        keys(definition["parameters"], default["parameters"], definition["name"])
        for key, v in definition["parameters"].items():
            if key == "anti_windup":
                if type(v) is not bool: raise ValueError("anti_windup必须为布尔值")
            elif type(v) not in (int, float): raise ValueError("控制器参数必须为实数")
        controller_for(definition["name"], definition["parameters"])
        params = definition["parameters"]
        if definition["name"] == "PI" and (params["kd"] != 0 or params["anti_windup"]):
            raise ValueError("PI定义要求kd=0且关闭抗饱和；请使用PID_aw调整微分与抗饱和参数")
        if definition["name"] in ("PID_aw", "TwoDOF_PID") and not params["anti_windup"]:
            raise ValueError("抗饱和PID与二自由度PID需启用anti_windup")
    for k, v in config["plant"].items():
        if type(v) not in (int, float): raise ValueError("对象参数必须为实数")
    MODELS[config["model"]](**config["plant"])
    c = config["conditions"]
    for k, v in c.items():
        if k == "recovery_mode":
            if v not in ("auto", "settling", "tracking_only"): raise ValueError("恢复判定模式无效")
        elif type(v) not in (int, float): raise ValueError("实验条件必须为实数")
    if type(c["seed"]) is not int or not 0 <= c["seed"] < 2**32: raise ValueError("噪声种子必须为非负整数")
    if c["reference_scale"] <= 0: raise ValueError("参考尺度必须为正")
    s = scenario_for(config)
    for definition in definitions:
        if definition["name"] in names and definition["name"] == "LADRC" and definition["parameters"]["observer_bandwidth"]*s.dt_s > 0.2+1e-14:
            raise ValueError("LADRC观察器带宽×采样周期需≤0.2，请降低带宽或减小采样周期")
    return config


def scenario_for(config):
    c = config["conditions"]
    ref, disturbance = (make_signal(config[k], c) for k in ("reference", "disturbance"))
    mode = c["recovery_mode"]
    if mode == "auto":
        mode = "settling" if ref.constant_after(c["recovery_start_s"]) and disturbance.constant_after(c["recovery_start_s"]) else "tracking_only"
    args = {k: v for k, v in c.items() if k not in ("input_limit", "reference_scale", "recovery_mode")}
    return Scenario(name=config["name"], reference=ref, load=disturbance, voltage_limit=c["input_limit"], recovery_mode=mode, **args)


def execute(output, value, *, plots=False, progress=None, should_cancel=None):
    config = validate_config(value)
    s = scenario_for(config)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    expected, records = len(config["selected_controllers"]), []
    spec = dict(spec_for(config["model"]), scale=config["conditions"]["reference_scale"], limit=s.voltage_limit)
    manifest = dict(schema_version="experiment-1.0", package_version=__version__, python=platform.python_version(),
        evidence="synthetic_assumption", hardware_validated=False, config=config, expected_runs=expected,
        units=spec["units"], source_files_sha256={p.name: sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}, artifacts_complete=False)
    atomic_json(output / "status.json", batch_status("in_progress", expected, 0, 0))

    def checkpoint(stage):
        if should_cancel and should_cancel(): raise Cancelled("用户请求取消；已完成记录保留")
        if progress: progress(dict(event="progress", stage=stage, written=len(records), expected=expected,
                                   failed=sum(r["metrics"]["status"] != "completed" for r in records)))

    try:
        (output / "runs").mkdir()
        atomic_json(output / "config.json", config)
        atomic_json(output / "inputs.json", dict(scenario=asdict(s), noise=s.noise_sequence(), units=spec["units"]))
        manifest.update(config_sha256=sha(output / "config.json"), input_sha256=sha(output / "inputs.json"))
        atomic_json(output / "manifest.json", manifest)
        for name in config["selected_controllers"]:
            checkpoint("运行 "+name)
            params = next(x["parameters"] for x in config["controllers"] if x["name"] == name)
            run = simulate(MODELS[config["model"]](**config["plant"]), controller_for(name, params), s)
            trace = "runs/"+name+".csv"
            write_csv(output / trace, [{new: row[old] for new, old in COLUMN_MAP.items()} for row in run.rows])
            metrics = neutral_metrics(run, spec)
            metrics["input_variation_rate"] = None if metrics["normalized_input_variation"] is None else metrics["normalized_input_variation"]/(s.duration_s-s.evaluation_start_s)
            record = dict(case_id=name, model_name=config["model"], controller_name=name, plant=run.plant,
                controller=run.controller, scenario=asdict(s), units=spec["units"], reference_scale=spec["scale"], input_limit=s.voltage_limit,
                input_file="inputs.json", input_sha256=manifest["input_sha256"], trace_file=trace, trace_file_sha256=sha(output / trace), metrics=metrics, failure=run.failure)
            atomic_json(output / ("runs/"+name+".json"), record)
            records.append(record)
            atomic_json(output / "status.json", batch_status("in_progress", expected, len(records), sum(r["metrics"]["status"] != "completed" for r in records)))
        checkpoint("保存图表与报告")
        atomic_json(output / "results.json", records)
        if plots:
            from .experiment_plots import build
            build(output, records)
        checkpoint("保存校验清单")
        rows = "".join("<tr>"+"".join("<td>"+html.escape(str(x))+"</td>" for x in
            (r["controller_name"], r["metrics"]["status"], r["metrics"]["rmse"], r["metrics"]["iae"], r["metrics"]["input_total_variation"], r["metrics"]["saturation_fraction"], r["metrics"]["recovery_status"]))+"</tr>" for r in records)
        images = "".join(f'<a href="figures/{p.name}"><img src="figures/{p.name}"></a>' for p in sorted((output / "figures").glob("*.png")))
        (output / "report.html").write_text(f'''<!doctype html><meta charset="utf-8"><title>ControlStressLab 实验报告</title>
<style>body{{font:16px sans-serif;line-height:1.7;max-width:1200px;margin:30px auto;padding:20px}}table{{border-collapse:collapse}}td,th{{padding:8px;border:1px solid #ddd}}img{{max-width:100%}}</style>
<h1>{html.escape(config['name'])}</h1><p>合成模型，未经硬件验证。各控制器共用相同参考、扰动、噪声、限幅和评价窗口；不同指标分别解释，不预设普遍赢家。</p>
<p>对象：{config['model']}；输出单位{spec['units']['output']}，输入单位{spec['units']['input']}，IAE单位为输出单位×s。
评价窗口{s.evaluation_start_s}—{s.duration_s} s；恢复模式{s.recovery_mode}。持续变化输入的恢复可为不适用，失败指标为null，不作零误差。</p>
<p><a href="config.json">实际配置</a> · <a href="inputs.json">配对输入</a> · <a href="results.json">逐次结果</a> · <a href="manifest.json">源码指纹</a> · <a href="status.json">产物状态</a></p>
<table><tr><th>控制器</th><th>执行状态</th><th>RMSE</th><th>IAE</th><th>输入总变化量</th><th>饱和比例</th><th>恢复判定</th></tr>{rows}</table>{images}
<p>完整轨迹位于runs目录。恢复时间不是稳定性证明，输入变化量不是能耗；数据和图片保留完整观察窗口。</p>''', encoding="utf8")
        failed = sum(r["metrics"]["status"] != "completed" for r in records)
        manifest.update(written_runs=len(records), failed_runs=failed, artifacts_complete=True)
        atomic_json(output / "manifest.json", manifest)
        final = batch_status("completed_with_failures" if failed else "completed", expected, len(records), failed, complete=True)
        status_bytes = json.dumps(final, indent=2, ensure_ascii=False, allow_nan=False).encode("utf8")
        hashes = {p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob("*")) if p.is_file() and p.name != "status.json"}
        hashes["status.json"] = hashlib.sha256(status_bytes).hexdigest()
        atomic_json(output / "checksums.json", hashes)
        temp = output / "status.json.tmp"
        temp.write_bytes(status_bytes)
        temp.replace(output / "status.json")
        if progress: progress(dict(event="completed", written=len(records), expected=expected, failed=failed, report=str(output / "report.html")))
        return output / "report.html", failed
    except BaseException as exc:
        manifest["artifacts_complete"] = False
        for name, data in (("manifest.json", manifest), ("status.json", batch_status("interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "export_failure", expected, len(records), sum(r["metrics"]["status"] != "completed" for r in records), error=exc))):
            try: atomic_json(output / name, data)
            except Exception: pass
        raise


def contained(folder, relative):
    path = (folder / relative).resolve()
    if not path.is_relative_to(folder.resolve()): raise ValueError("结果文件路径超出实验目录")
    return path


def load_result(folder):
    """Read saved metrics, never silently recompute old experiments."""
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf8"))
    status = json.loads((folder / "status.json").read_text(encoding="utf8"))
    verification, problems = "未提供校验", []
    if (folder / "checksums.json").is_file():
        checks = json.loads((folder / "checksums.json").read_text(encoding="utf8"))
        if not isinstance(checks, dict) or not checks:
            raise ValueError("校验清单为空或格式无效")
        for required in ("manifest.json", "status.json"):
            if required not in checks: problems.append(required+" 未受校验")
        for name, expected in checks.items():
            p = contained(folder, name)
            if not p.is_file() or sha(p) != expected: problems.append(name)
        listed = set(checks)
        # Preserved historical suites have a second checksum layer for source
        # snapshots and their archive README; those are not original run files.
        archive_path = folder / "archive_manifest.json"
        if archive_path.is_file():
            archive = json.loads(archive_path.read_text(encoding="utf8")).get("files_sha256")
            if not isinstance(archive, dict) or not archive: raise ValueError("归档校验清单无效")
            for name, expected in archive.items():
                p = contained(folder, name)
                if not p.is_file() or sha(p) != expected: problems.append(name)
            listed.update(archive)
            listed.add("archive_manifest.json")
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p.name != "checksums.json"}
        problems.extend(sorted(actual - listed))
        verification = "校验不一致" if problems else "校验通过"
    if manifest.get("schema_version") == "experiment-1.0":
        records = json.loads((folder / "results.json").read_text(encoding="utf8")) if (folder / "results.json").exists() else [json.loads(p.read_text(encoding="utf8")) for p in sorted((folder / "runs").glob("*.json"))]
    elif manifest.get("schema_version") in ("coverage-1.0", "benchmark-1.0"):
        records = [json.loads(p.read_text(encoding="utf8")) for p in sorted((folder / "runs").glob("*.json"))]
    else:
        records = []  # Historical motor scans retain their original HTML/schema.
    return dict(folder=folder, manifest=manifest, status=status, records=records, verification=verification, problems=problems)


def read_trace(folder, record):
    with contained(Path(folder), record["trace_file"]).open(encoding="utf8", newline="") as stream:
        return [{k: (float(v) if v else None) for k, v in row.items() if k not in ("action_taken", "transition_completed")} for row in csv.DictReader(stream)]


def saved_reference(record):
    """Full saved reference, including the unobserved tail of failed runs."""
    signal, duration = record["scenario"]["reference"], record["scenario"]["duration_s"]
    if "values" in signal:
        return [i*signal["dt_s"] for i in range(len(signal["values"]))], signal["values"]
    points = signal["points"]
    return [p[0] for p in points]+[duration], [p[1] for p in points]+[points[-1][1]]


def export_zip(folder, destination, *, should_cancel=None):
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    if destination.exists(): raise FileExistsError("目标ZIP已存在，请使用新文件名")
    if destination.is_relative_to(folder): raise ValueError("ZIP必须保存在实验目录之外")
    loaded = load_result(folder)
    if not loaded["status"].get("artifacts_complete") or loaded["verification"] != "校验通过":
        raise ValueError("实验未完整保存或校验未通过，不能导出为完整报告")
    if any(p.is_symlink() for p in folder.rglob("*")): raise ValueError("实验中不支持符号链接")
    files = [p for p in sorted(folder.rglob("*")) if p.is_file()]
    temporary = destination.with_name(destination.name+".partial-"+uuid.uuid4().hex[:8])
    def checkpoint():
        if should_cancel and should_cancel(): raise Cancelled("报告导出已取消；未完成ZIP以.partial文件保留")
    checkpoint()
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as stream:
        for p in files:
            checkpoint()
            stream.write(p, folder.name+"/"+p.relative_to(folder).as_posix())
    with zipfile.ZipFile(temporary) as stream:
        if stream.testzip() is not None: raise ValueError("ZIP内容校验失败")
        for p in files:
            checkpoint()
            if hashlib.sha256(stream.read(folder.name+"/"+p.relative_to(folder).as_posix())).hexdigest() != sha(p): raise ValueError("ZIP与原始文件不一致")
    checkpoint()
    if destination.exists(): raise FileExistsError("目标ZIP已存在，未覆盖")
    temporary.rename(destination)
    return destination


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
