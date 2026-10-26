"""Immutable selection receipts, paired validation and observation history."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

from . import analysis_artifacts as artifacts
from .experiment import atomic_json, keys, load_result, sha


def verified(folder, schema):
    loaded = load_result(folder)
    if loaded["manifest"].get("schema_version") != schema: raise ValueError("来源类型不匹配："+schema)
    if loaded["verification"] != "校验通过" or not loaded["status"].get("artifacts_complete"): raise ValueError("来源必须完整且校验通过")
    if any(p.is_symlink() for p in Path(folder).rglob("*")): raise ValueError("来源不支持符号链接")
    return loaded


def _registry(parent):
    path = Path(parent)/"tuning-observations.json"
    data = json.loads(path.read_text(encoding="utf8")) if path.exists() else dict(schema="tuning-observations-1.0",inputs={})
    if not isinstance(data,dict) or data.get("schema")!="tuning-observations-1.0" or not isinstance(data.get("inputs"),dict): raise ValueError("验证观察历史损坏，不能声明新工况")
    return path,data


def check_unobserved(parent, hashes):
    _,data = _registry(parent)
    if set(hashes) & data["inputs"].keys(): raise ValueError("验证计划包含本工作区已启用的验证输入；请声明新验证条件")


@contextmanager
def _registry_lock(parent):
    lock = Path(parent)/"tuning-observations.lock"
    try: fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc: raise ValueError("另一任务正在更新验证观察历史，请稍后重试") from exc
    try:
        os.close(fd)
        yield
    finally: lock.unlink()


def reserve_observations(parent, hashes, receipt_sha):
    with _registry_lock(parent):
        path,data = _registry(parent)
        old = [data["inputs"][h] for h in hashes if h in data["inputs"]]
        if any(v["selection_sha256"] != receipt_sha for v in old): raise ValueError("这些验证输入已用于另一份选择记录；不能再次视为未参与选择")
        for h in hashes: data["inputs"][h] = dict(selection_sha256=receipt_sha,started_utc=datetime.now(timezone.utc).isoformat())
        atomic_json(path,data)
    return "reproduction_same_frozen_selection" if old else "first_use_in_workspace"


def freeze(output, request, *, plots=False, progress=None, should_cancel=None):
    from .tuning import checkpoint, source_snapshot
    keys(request,("search_folder","candidate_ids","main_candidate_id",*(("rationale",) if "rationale" in request else ())),"冻结选择")
    if "rationale" in request and (not isinstance(request["rationale"],str) or len(request["rationale"])>4000):raise ValueError("选择依据需要4000字以内文本")
    folder = Path(request["search_folder"]).resolve()
    if Path(output).resolve().is_relative_to(folder): raise ValueError("冻结输出必须位于搜索目录之外")
    loaded = verified(folder,"tuning-search-1.0")
    summary = json.loads((folder/"summary.json").read_text(encoding="utf8"))
    ids,main = request["candidate_ids"],request["main_candidate_id"]
    if not isinstance(ids,list) or not 1<=len(ids)<=2 or any(type(i)is not int for i in ids) or len(set(ids))!=len(ids) or type(main)is not int or main not in ids: raise ValueError("选择1～2个可行候选，并事先指定其中一个为主选")
    found = {c["candidate_id"]:c for c in summary["candidates"]}
    if any(i not in found or not found[i]["feasible"] for i in ids): raise ValueError("只能冻结完整搜索中的可行候选；无可行方案不回退")
    selection = dict(schema="tuning-selection-1.0",search_folder=str(folder),search_manifest_sha256=sha(folder/"manifest.json"),
        search_checksums_sha256=sha(folder/"checksums.json"),config_sha256=sha(folder/"config.json"),plan_sha256=sha(folder/"plan.json"),
        candidate_ids=ids,main_candidate_id=main,candidates=[deepcopy(found[i]) for i in ids],
        frozen_utc=datetime.now(timezone.utc).isoformat(),validation_ranking_allowed=False)
    if "rationale" in request:selection["rationale"]=request["rationale"]
    checkpoint("冻结主选和验证计划",[],0,progress,should_cancel)
    output,manifest = artifacts.begin(output,"tuning-selection-1.0",loaded["manifest"]["config"],0)
    try:
        for name in ("config.json","plan.json","summary.json"):
            (output/("search-summary.json" if name=="summary.json" else name)).write_bytes((folder/name).read_bytes())
        atomic_json(output/"selection.json",selection)
        source_snapshot(output)
        (output/"report.html").write_text('<!doctype html><meta charset="utf-8"><h1>参数与主选已冻结；尚未验证</h1><p>主选候选：'+str(main)+'</p><p><a href="selection.json">选择记录</a> · <a href="config.json">协议</a> · <a href="plan.json">验证计划</a></p>',encoding="utf8")
        artifacts.finish(output,manifest,[],0)
        return output/"report.html",0
    except BaseException as exc:
        artifacts.interrupted(output,manifest,[],0,exc)
        raise


def execute(output, request, *, plots=False, progress=None, should_cancel=None):
    from .tuning import checkpoint, finalize, run_cases, source_snapshot
    keys(request,("selection_folder",),"新工况验证")
    selection_folder = Path(request["selection_folder"]).resolve()
    selection_loaded = verified(selection_folder,"tuning-selection-1.0")
    selection = json.loads((selection_folder/"selection.json").read_text(encoding="utf8"))
    from .projects import frozen_source
    folder = frozen_source(selection_folder,selection)
    destination = Path(output).resolve()
    if destination.is_relative_to(folder.resolve()) or destination.is_relative_to(selection_folder):
        raise ValueError("验证输出必须位于搜索与选择目录之外")
    loaded = verified(folder,"tuning-search-1.0")
    for name,key in (("manifest.json","search_manifest_sha256"),("checksums.json","search_checksums_sha256"),("config.json","config_sha256"),("plan.json","plan_sha256")):
        if sha(folder/name) != selection[key]: raise ValueError("冻结后搜索来源发生变化："+name)
    if sha(selection_folder/"config.json") != selection["config_sha256"] or sha(selection_folder/"plan.json") != selection["plan_sha256"]: raise ValueError("冻结协议或计划发生变化")
    config = loaded["manifest"]["config"]
    plan = json.loads((selection_folder/"plan.json").read_text(encoding="utf8"))
    source_candidates = {c["candidate_id"]:c for c in json.loads((folder/"summary.json").read_text(encoding="utf8"))["candidates"]}
    ids,main = selection["candidate_ids"],selection["main_candidate_id"]
    if not isinstance(ids,list) or not 1<=len(ids)<=2 or len(set(ids))!=len(ids) or main not in ids or selection["candidates"] != [source_candidates[i] for i in ids] or any(not source_candidates[i]["feasible"] for i in ids): raise ValueError("选择记录与已保存搜索候选不一致")
    ids = list(dict.fromkeys([0]+ids))
    candidates = [dict(candidate_id=i,parameters=source_candidates[i]["parameters"]) for i in ids]
    roles = {i:(["baseline"] if i==0 else [])+(["main"] if i==main else [])+(["comparison"] if i!=main and i in selection["candidate_ids"] else []) for i in ids}
    expected,records = len(candidates)*len(plan["validation"]),[]
    checkpoint("验证冻结指纹与输入历史",records,expected,progress,should_cancel)
    if Path(output).exists(): raise FileExistsError("目标验证目录已存在，未覆盖")
    observation = reserve_observations(folder.parent,[c["input_sha256"] for c in plan["validation"]],sha(selection_folder/"selection.json"))
    output,manifest = artifacts.begin(output,"tuning-validation-1.0",config,expected)
    manifest.update(execution_complete=False,requirements_met=None,selection_sha256=sha(selection_folder/"selection.json"),observation=observation,
                    validation_started_utc=datetime.now(timezone.utc).isoformat())
    try:
        for name in ("inputs","runs"): (output/name).mkdir()
        atomic_json(output/"config.json",config)
        atomic_json(output/"plan.json",plan)
        atomic_json(output/"selection.json",selection)
        atomic_json(output/"manifest.json",manifest)
        source_snapshot(output)
        checkpoint("保存搜索与冻结选择的独立快照",records,expected,progress,should_cancel)
        shutil.copytree(folder,output/"evidence/search")
        shutil.copytree(selection_folder,output/"evidence/selection")
        verified(output/"evidence/search","tuning-search-1.0")
        verified(output/"evidence/selection","tuning-selection-1.0")
        if sha(output/"evidence/search/checksums.json") != selection["search_checksums_sha256"]: raise ValueError("复制途中搜索来源发生变化")
        run_cases(output,config,plan["validation"],candidates,records,manifest,"validation",progress,should_cancel,roles)
        assessments = []
        for candidate in candidates:
            subset = [r for r in records if r["candidate_id"]==candidate["candidate_id"]]
            kinds = {r["requirement"] for r in subset}
            outcome = "run_failed" if "run_failed" in kinds else "metric_invalid" if "metric_invalid" in kinds else "not_met" if kinds!={"met"} else "met"
            assessments.append(dict(candidate_id=candidate["candidate_id"],roles=roles[candidate["candidate_id"]],outcome=outcome,
                runs=len(subset),issues=[dict(case_id=r["case_id"],**issue) for r in subset for issue in r["issues"]]))
        summary = dict(main_candidate_id=main,main_outcome=next(a["outcome"] for a in assessments if a["candidate_id"]==main),
                       candidates=assessments,observation=observation,validation_ranking_allowed=False)
        return finalize(output,manifest,config,summary,records,plots,progress,should_cancel)
    except BaseException as exc:
        artifacts.interrupted(output,manifest,records,sum(r["metrics"]["status"]!="completed" for r in records),exc)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command",required=True)
    f = subs.add_parser("freeze")
    f.add_argument("--search",type=Path,required=True); f.add_argument("--candidates",type=int,nargs="+",required=True); f.add_argument("--main",type=int,required=True)
    v = subs.add_parser("run")
    v.add_argument("--selection",type=Path,required=True); v.add_argument("--plots",action="store_true")
    for p in (f,v): p.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if args.command=="freeze": report,failed=freeze(args.output,dict(search_folder=str(args.search),candidate_ids=args.candidates,main_candidate_id=args.main))
    else: report,failed=execute(args.output,dict(selection_folder=str(args.selection)),plots=args.plots)
    print(report)
    if failed: parser.exit(1)


if __name__ == "__main__": main()
