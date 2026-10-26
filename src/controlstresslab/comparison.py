"""Verified cross-experiment comparison. Original metrics are read, never rerun."""
import argparse
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path

from . import analysis_artifacts as artifacts
from .cli import write_csv
from .experiment import Cancelled, atomic_json, contained, keys, load_result, read_trace, sha


def digest_json(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode("utf8")).hexdigest()


def signal_context(signal):
    return dict(recipe=signal.get("recipe", {}), dt_s=signal.get("dt_s"),
        sampled_values_sha256=digest_json(signal.get("values", signal.get("points"))),
        sample_count=len(signal.get("values", signal.get("points", []))))


def record_context(record):
    scenario = record["scenario"]
    return dict(model=record["model_name"], plant=record["plant"],
        controller=dict(name=record["controller_name"], parameters=record["controller"]),
        conditions={k:v for k,v in scenario.items() if k not in ("name", "evidence", "reference", "load")},
        reference=signal_context(scenario["reference"]), disturbance=signal_context(scenario["load"]),
        reference_scale=record["reference_scale"], input_limit=record["input_limit"], units=record["units"])


def flatten(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items(): result.update(flatten(item, (prefix+"." if prefix else "")+key))
    else: result[prefix] = value
    return result


def differences(before, after):
    a, b = flatten(before), flatten(after)
    return [dict(field=k, before=a.get(k), after=b.get(k)) for k in sorted(set(a)|set(b)) if a.get(k) != b.get(k)]


def build(entries, *, cached_sources=None):
    if not isinstance(entries, list) or not 2 <= len(entries) <= 8: raise ValueError("选择2～8条独立轨迹进行对照")
    cached_sources = {} if cached_sources is None else cached_sources
    views, seen = [], set()
    for entry in entries:
        keys(entry, ("folder", "case_id", "label"), "对照条目")
        if not all(isinstance(entry[k], str) and entry[k].strip() for k in entry): raise ValueError("实验目录、工况和标签不能为空")
        if len(entry["label"]) > 70: raise ValueError("轨迹标签不超过70字符")
        folder = Path(entry["folder"]).resolve()
        identity = (str(folder), entry["case_id"])
        if identity in seen: raise ValueError("同一原始轨迹不能重复加入")
        seen.add(identity)
        key = str(folder)
        loaded = cached_sources.get(key)
        if loaded is None:
            loaded = load_result(folder)
            cached_sources[key] = loaded
        if loaded["verification"] != "校验通过" or not loaded["status"].get("artifacts_complete"):
            raise ValueError("仅支持完整且校验通过的历史实验："+folder.name)
        found = [r for r in loaded["records"] if r["case_id"] == entry["case_id"]]
        if len(found) != 1: raise ValueError("未找到唯一工况："+entry["case_id"])
        record = found[0]
        if views and record["units"] != views[0]["record"]["units"]: raise ValueError("物理单位不一致，不能叠加比较")
        views.append(dict(entry=deepcopy(entry), folder=folder, record=record, manifest=loaded["manifest"],
            manifest_sha256=sha(folder/"manifest.json"), context=record_context(record), rows=read_trace(folder, record)))
    diff, warnings = [], []
    for view in views[1:]:
        changes = differences(views[0]["context"], view["context"])
        diff.append(dict(label=view["entry"]["label"], reference_label=views[0]["entry"]["label"], changes=changes))
        changed = {c["field"] for c in changes}
        windows = {"conditions.dt_s", "conditions.duration_s", "conditions.evaluation_start_s", "conditions.recovery_start_s", "conditions.recovery_band", "conditions.recovery_dwell_s", "conditions.recovery_mode", "reference_scale"}
        if changed & windows: warnings.append(view["entry"]["label"]+"：采样、评价/恢复窗口或归一化尺度不同，指标不宜直接横比")
        factors = {c["field"] for c in changes if c["field"].startswith(("plant.", "conditions."))}
        for group in ("controller", "reference", "disturbance"):
            if any(c["field"].startswith(group+".") for c in changes): factors.add(group)
        if len(factors) > 1: warnings.append(view["entry"]["label"]+"：多项对象/条件同时变化，仅作多因素描述")
        if view["manifest"].get("package_version") != views[0]["manifest"].get("package_version"):
            warnings.append(view["entry"]["label"]+"：来源软件版本不同")
    return dict(views=views, differences=diff, warnings=warnings,
        note="原始指标只读；坐标共用物理单位，不自动归一化，不推断单因素因果或算法普遍排名")


def execute(output, value, *, plots=False, progress=None, should_cancel=None):
    keys(value, ("schema", "entries"), "实验对照")
    if value["schema"] != "comparison-1.0": raise ValueError("未知对照版本")
    # Fresh verification on export, independent of any GUI import-time cache.
    compared = build(value["entries"])
    records, failed = [], 0
    output, manifest = artifacts.begin(output, "comparison-1.0", value, len(compared["views"]))
    def checkpoint(stage):
        if should_cancel and should_cancel(): raise Cancelled("对照导出已取消，已有快照保留")
        if progress: progress(dict(event="progress", stage=stage, written=len(records), expected=len(compared["views"]), failed=failed))
    try:
        (output/"runs").mkdir(); (output/"sources").mkdir()
        atomic_json(output/"config.json", value)
        for index, view in enumerate(compared["views"]):
            checkpoint("复制已校验轨迹 "+view["entry"]["label"])
            source = view["record"]
            if sha(view["folder"]/"manifest.json") != view["manifest_sha256"]: raise ValueError("来源清单在复制前发生变化")
            record = deepcopy(source)
            case_id = f"trace_{index:02d}"
            trace = "runs/"+case_id+".csv"
            raw = contained(view["folder"], source["trace_file"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != source["trace_file_sha256"]: raise ValueError("原始轨迹在复制前发生变化")
            (output/trace).write_bytes(raw)
            source_prefix = f"sources/{case_id}"
            atomic_json(output/(source_prefix+"-manifest.json"), view["manifest"])
            atomic_json(output/(source_prefix+"-record.json"), source)
            input_raw = contained(view["folder"], source["input_file"]).read_bytes()
            if hashlib.sha256(input_raw).hexdigest() != source["input_sha256"]: raise ValueError("配对输入在复制前发生变化")
            (output/(source_prefix+"-inputs.json")).write_bytes(input_raw)
            record.update(case_id=case_id, trace_file=trace, trace_file_sha256=sha(output/trace),
                input_file=source_prefix+"-inputs.json", comparison_label=view["entry"]["label"],
                source=dict(folder=str(view["folder"]), case_id=source["case_id"], trace_sha256=source["trace_file_sha256"],
                    manifest_sha256=view["manifest_sha256"], package_version=view["manifest"].get("package_version")))
            atomic_json(output/("runs/"+case_id+".json"), record)
            records.append(record)
            failed += record["metrics"]["status"] != "completed"
            artifacts.checkpoint(output, manifest, records, failed)
        summary = {k:v for k,v in compared.items() if k != "views"}
        atomic_json(output/"comparison.json", summary)
        write_csv(output/"metrics.csv", [dict(label=r["comparison_label"], case_id=r["case_id"], **r["metrics"]) for r in records])
        checkpoint("保存对照图与报告")
        if plots:
            from .comparison_plots import build as charts
            charts(output, records)
        diffs = "".join("<h3>"+html.escape(d["label"])+" / 对照 "+html.escape(d["reference_label"])+"</h3><pre>"+html.escape(json.dumps(d["changes"],indent=2,ensure_ascii=False))+"</pre>" for d in summary["differences"])
        images = "".join(f'<img src="figures/{p.name}">' for p in sorted((output/"figures").glob("*.png")))
        rows = "".join("<tr>"+"".join("<td>"+html.escape(str(v))+"</td>" for v in (r["comparison_label"], r["metrics"]["status"], r["metrics"]["rmse"],r["metrics"]["iae"],r["metrics"]["input_total_variation"],r["metrics"]["saturation_fraction"]))+"</tr>" for r in records)
        (output/"report.html").write_text('''<!doctype html><meta charset="utf-8"><title>ControlStressLab 跨实验对照</title><style>body{font:16px sans-serif;max-width:1200px;margin:30px auto;padding:20px;line-height:1.7}img{max-width:100%}td,th{border:1px solid #ddd;padding:8px}table{border-collapse:collapse}pre{white-space:pre-wrap}</style><h1>跨实验结果对照</h1><p>原始指标不重算，完整轨迹和配对输入已复制到本报告；来源目录移走后仍可读取快照。</p><p>'''+html.escape(summary["note"])+"</p><p>"+html.escape("；".join(summary["warnings"]))+'''</p><p><a href="comparison.json">变化字段与提示</a> · <a href="metrics.csv">原始指标</a> · <a href="config.json">来源与标签</a> · <a href="manifest.json">来源清单</a></p><table><tr><th>轨迹</th><th>状态</th><th>RMSE</th><th>IAE</th><th>输入变化量</th><th>饱和比例</th></tr>'''+rows+"</table>"+images+diffs,encoding="utf8")
        checkpoint("提交对照快照")
        artifacts.finish(output, manifest, records, failed)
        return output/"report.html", failed
    except BaseException as exc:
        artifacts.interrupted(output, manifest, records, failed, exc)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    report, failed = execute(args.output,json.loads(args.config.read_text(encoding="utf8")),plots=args.plots)
    print(report)
    if failed: parser.exit(1)


if __name__ == "__main__": main()
