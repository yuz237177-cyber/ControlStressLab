"""Finite feasible-candidate tradeoffs. Validation results have no input here."""
import math
from .tuning_protocol import THRESHOLDS


def checks(metrics, thresholds):
    if metrics["status"] != "completed": return [dict(kind="run_failed",metric="status",value=metrics["status"],threshold=None)]
    issues = []
    for name in THRESHOLDS.values():
        value = metrics.get(name)
        if type(value) not in (float,int) or not math.isfinite(value):
            issues.append(dict(kind="metric_invalid",metric=name,value=None,threshold=None))
    if issues: return issues
    for key,name in THRESHOLDS.items():
        limit = thresholds[key]
        if limit is not None and metrics[name] > limit:
            issues.append(dict(kind="not_met",metric=name,value=metrics[name],threshold=limit))
    return issues


def assess(records, thresholds, expected):
    issues = [dict(case_id=r["case_id"],**issue) for r in records for issue in checks(r["metrics"],thresholds)]
    if len(records) != expected: issues.append(dict(case_id=None,kind="incomplete",metric="run_count",value=len(records),threshold=expected))
    if issues: return dict(feasible=False,J1=None,J2=None,issues=issues,worst_error_case=None,worst_action_case=None)
    families = {}
    for r in records:
        cells = families.setdefault(r["family"],{})
        cells.setdefault(r["condition_index"],[]).append(r["metrics"]["normalized_rmse"])
    if not families: return dict(feasible=False,J1=None,J2=None,issues=[dict(kind="incomplete")],worst_error_case=None,worst_action_case=None)
    j1 = sum(sum(max(v) for v in cells.values())/len(cells) for cells in families.values())/len(families)
    worst_e = max(records,key=lambda r:r["metrics"]["normalized_rmse"])
    worst_v = max(records,key=lambda r:r["metrics"]["input_variation_rate"])
    return dict(feasible=True,J1=j1,J2=worst_v["metrics"]["input_variation_rate"],issues=[],
                worst_error_case=worst_e["case_id"],worst_action_case=worst_v["case_id"])


def summarize(candidates, records, config, expected):
    if any(r.get("subset","search")!="search" for r in records): raise ValueError("候选选择只接收搜索阶段指标，禁止验证结果进入选择器")
    values = [dict(candidate,**assess([r for r in records if r["candidate_id"]==candidate["candidate_id"]],config["thresholds"],expected)) for candidate in candidates]
    feasible = [c for c in values if c["feasible"]]
    front = [a["candidate_id"] for a in feasible if not any(
        b["J1"]<=a["J1"] and b["J2"]<=a["J2"] and (b["J1"]<a["J1"] or b["J2"]<a["J2"]) for b in feasible)]
    return dict(candidates=values,frontier_ids=front,feasible_count=len(feasible),
                low_error_id=min(feasible,key=lambda c:(c["J1"],c["J2"],c["candidate_id"]))["candidate_id"] if feasible else None,
                smooth_action_id=min(feasible,key=lambda c:(c["J2"],c["J1"],c["candidate_id"]))["candidate_id"] if feasible else None)
