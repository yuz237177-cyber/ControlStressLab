"""Saved sampled-data loop analysis; finite-band margins and uncancelled poles."""
import argparse
from copy import deepcopy
import html,json,math
from pathlib import Path
import numpy as np
from scipy.optimize import brentq,minimize_scalar
from . import analysis_artifacts as artifacts
from .cli import write_csv
from .experiment import Cancelled,atomic_json,default_config as experiment_config,finite_tree,keys,validate_config as validate_experiment
from .frequency_model import SUPPORTED,compile_model,response,pole_summary

def default_config(base=None):
    base=deepcopy(base) if base is not None else experiment_config()
    base["selected_controllers"]=[n for n in base["selected_controllers"] if n in SUPPORTED]
    if not base["selected_controllers"]:raise ValueError("当前选择中没有受支持的PI/PID族；LADRC暂不支持频域分析")
    return dict(schema="frequency-config-1.0",base=base,omega_min=.01,omega_max=min(100.,.9*math.pi/base["conditions"]["dt_s"]),
        points=1024,max_points=8192,source=None)

def validate_config(value):
    finite_tree(value);keys(value,default_config(),"频域分析");c=deepcopy(value)
    if c["schema"]!="frequency-config-1.0":raise ValueError("未知频域版本")
    c["base"]=validate_experiment(c["base"])
    if any(n not in SUPPORTED for n in c["base"]["selected_controllers"]):raise ValueError("频域不支持LADRC，请选择PI/PID族")
    if any(type(c[k]) not in (int,float) for k in ("omega_min","omega_max")) or not 0<c["omega_min"]<c["omega_max"]<math.pi/c["base"]["conditions"]["dt_s"]:raise ValueError("频段需要0 < 下限 < 上限 < 奈奎斯特频率")
    if type(c["points"]) is not int or not 256<=c["points"]<=4096 or type(c["max_points"]) is not int or not c["points"]+64<=c["max_points"]<=16384:raise ValueError("基础点数256～4096，总频率网格预算≤16384")
    for name in c["base"]["selected_controllers"]:compile_model(c["base"],name)
    if c["source"] is not None:
        keys(c["source"],("folder","case_id","manifest_sha256","producer_version"),"频域来源")
        from .experiment import load_result,sha
        folder=Path(c["source"]["folder"]);loaded=load_result(folder)
        if loaded["verification"]!="校验通过" or sha(folder/"manifest.json")!=c["source"]["manifest_sha256"]:raise ValueError("分析来源校验失败")
        original=loaded["manifest"]["config"] if loaded["manifest"]["schema_version"]=="experiment-1.0" else next((r["run_config"] for r in loaded["records"] if r["case_id"]==c["source"]["case_id"]),None)
        if original is None:raise ValueError("来源工况不存在")
        original=deepcopy(original);original["selected_controllers"]=c["base"]["selected_controllers"]
        if original!=c["base"] or c["source"]["producer_version"]!=loaded["manifest"]["package_version"]:raise ValueError("分析配置与冻结来源不一致；请从实验草稿建立新分析")
    return c

def grid(model,c):
    count=min(c["max_points"]-64,max(c["points"],4*c["points"]))
    w=list(np.geomspace(c["omega_min"],c["omega_max"],count))
    for p in np.linalg.eigvals(model["plant"]["A"]):
        center=abs(float(np.angle(p)))/model["dt_s"]
        if not c["omega_min"]<center<c["omega_max"]:continue
        width=max(abs(math.log(max(abs(p),1e-300)))/model["dt_s"],center*1e-10)
        for factor in (-100,-10,-1,-.1,-.01,0,.01,.1,1,10,100):
            v=center+factor*width
            if c["omega_min"]<v<c["omega_max"]:w.append(v)
    return np.array(sorted(set(w)))[:c["max_points"]]

def crossovers(model,w,values,phase):
    entries=[];unresolved=[]
    loop=values["L"]
    def function(logw,kind):
        value=response(model,[math.exp(logw)])["L"][0]
        if not np.isfinite(value) or abs(value)==0:return float("nan")
        return float(math.log(abs(value))) if kind=="gain" else float(value.imag/abs(value))
    x=np.log(w)
    for kind in ("gain","phase"):
        f=np.log(np.maximum(abs(loop),1e-300)) if kind=="gain" else np.divide(loop.imag,abs(loop),out=np.full(len(loop),np.nan),where=abs(loop)>0)
        roots=[]
        for i in range(len(w)-1):
            if not np.isfinite(f[i:i+2]).all():continue
            if f[i]==0:roots.append(x[i])
            elif f[i]*f[i+1]<0:
                try:roots.append(brentq(lambda v:function(v,kind),x[i],x[i+1],xtol=1e-12))
                except (ValueError,RuntimeError):unresolved.append(dict(kind=kind,low=float(w[i]),high=float(w[i+1])))
        # Local minimization also looks for tangencies rather than sign changes only.
        for i in range(1,len(w)-1):
            if not np.isfinite(f[i-1:i+2]).all():continue
            if abs(f[i])<min(abs(f[i-1]),abs(f[i+1])) and abs(f[i])<.05:
                result=minimize_scalar(lambda v:abs(function(v,kind)),bounds=(x[i-1],x[i+1]),method="bounded",options=dict(xatol=1e-12))
                if result.fun<1e-7:roots.append(result.x)
                elif result.fun<1e-4:unresolved.append(dict(kind=kind,low=float(w[i-1]),high=float(w[i+1])))
        for logw in sorted(roots):
            omega=math.exp(logw)
            if any(e["kind"]==kind and abs(math.log(e["omega_rad_s"]/omega))<1e-6 for e in entries):continue
            value=response(model,[omega])["L"][0]
            if not np.isfinite(value) or abs(value)==0 or kind=="phase" and value.real>=0:continue
            residual=abs(function(logw,kind))
            if residual>1e-6:unresolved.append(dict(kind=kind,low=omega,high=omega));continue
            entries.append(dict(kind=kind,omega_rad_s=omega,residual=residual,status="refined",
                gm=float(1/abs(value)) if kind=="phase" else None,gm_db=float(-20*math.log10(abs(value))) if kind=="phase" else None,
                pm_deg=float((np.angle(value,deg=True)+360)%360-180) if kind=="gain" else None,
                phase_unwrapped_deg=float(np.interp(logw,x,phase)),method="log-grid + brentq + local tangency minimization"))
    return entries,unresolved

def calculate(model,c):
    w=grid(model,c);values=response(model,w)
    no_delay=values.pop("loop_without_delay")
    valid=np.isfinite(no_delay)&(abs(no_delay)>0)
    phase=np.full(len(w),np.nan)
    # Unwrap only contiguous finite segments; delay's full phase is analytic.
    for indices in np.split(np.flatnonzero(valid),np.where(np.diff(np.flatnonzero(valid))>1)[0]+1):
        if len(indices):phase[indices]=np.unwrap(np.angle(no_delay[indices]))*180/math.pi-w[indices]*model["delay_samples"]*model["dt_s"]*180/math.pi
    entries,unresolved=crossovers(model,w,values,phase)
    singular=any(not np.isfinite(v).all() for v in values.values())
    phase_jump=bool(np.any(np.abs(np.diff(phase))>45))
    status="resolution_limited" if unresolved or phase_jump else "singular_samples" if singular else "finite_band"
    margins={}
    for kind,key in (("phase","gm"),("gain","pm_deg")):
        group=[e for e in entries if e["kind"]==kind]
        selected=min(group,key=lambda e:abs(e[key] if key=="pm_deg" else e["gm_db"])) if group else None
        margins[key]=dict(value=selected[key] if selected and status=="finite_band" else None,
            omega_rad_s=selected["omega_rad_s"] if selected and status=="finite_band" else None,
            reason="minimum_absolute_margin_in_band" if selected and status=="finite_band" else status if status!="finite_band" else "not_found_in_band")
    rows=[]
    for i,omega in enumerate(w):
        row=dict(omega_rad_s=float(omega),loop_phase_deg=float(phase[i]) if math.isfinite(phase[i]) else None)
        for key,arr in values.items():
            v=arr[i];finite=bool(np.isfinite(v));nonzero=finite and abs(v)>0
            row.update({key+"_real":float(v.real) if finite else None,key+"_imag":float(v.imag) if finite else None,
                key+"_magnitude":float(abs(v)) if finite else None,key+"_db":float(20*math.log10(abs(v))) if nonzero else None,
                key+"_status":"finite" if nonzero else "zero_channel" if finite else "singular_or_nonfinite"})
        rows.append(row)
    poles=pole_summary(model)
    summary=dict(controller=model["controller"],internal=poles,margin_status=status,margins=margins,crossovers=entries,
        unresolved_intervals=unresolved,frequency_points=len(w),
        sampled_peaks={key:float(max(abs(values[key][np.isfinite(values[key])]),default=0)) if np.isfinite(values[key]).any() else None for key in ("S","T")},
        scope="Detected finite-band crossovers; finite sampling is not a global root-count certificate. Positive margins do not prove internal or robust stability.")
    return summary,rows

def execute(output,value,*,plots=False,progress=None,should_cancel=None):
    from .projects import rebase_frequency
    c=validate_config(rebase_frequency(output,value));names=c["base"]["selected_controllers"]
    if c["source"] and Path(output).resolve().is_relative_to(Path(c["source"]["folder"]).resolve()):raise ValueError("分析输出必须位于冻结来源目录之外")
    if c["source"]:
        size=sum(p.stat().st_size for p in Path(c["source"]["folder"]).rglob("*") if p.is_file())
        if size>512*1024**2:raise ValueError("冻结来源超过512MB，请用实验草稿配置建立独立分析")
    out,manifest=artifacts.begin(output,"frequency-1.0",c,len(names));records=[]
    try:
        for d in ("models","frequency","validation","figures"):(out/d).mkdir()
        atomic_json(out/"config.json",c)
        if c["source"]:
            import shutil
            from .experiment import load_result,sha
            shutil.copytree(c["source"]["folder"],out/"evidence/source")
            if load_result(out/"evidence/source")["verification"]!="校验通过" or sha(out/"evidence/source/manifest.json")!=c["source"]["manifest_sha256"]:raise ValueError("冻结来源复制期间发生变化")
        for name in names:
            if should_cancel and should_cancel():raise Cancelled("频域分析已取消")
            if progress:progress(dict(stage="采样环路 / "+name,written=len(records),expected=len(names)))
            model=compile_model(c["base"],name);atomic_json(out/"models"/(name+".json"),model)
            summary,rows=calculate(model,c);write_csv(out/"frequency"/(name+".csv"),rows)
            folder=out/"validation"/name;folder.mkdir()
            from .frequency_validation import consistency,sine_check
            summary["time_check"],_=consistency(c["base"],model,folder,should_cancel)
            summary["sine_check"]=sine_check(c["base"],model,summary["internal"],folder,should_cancel)
            failed=any(summary[key]["state"]=="failed" for key in ("time_check","sine_check"))
            records.append(dict(case_id=name,controller_name=name,summary=summary,metrics=dict(status="consistency_failed" if failed else "completed")))
        atomic_json(out/"summary.json",[r["summary"] for r in records])
        write_csv(out/"poles.csv",[dict(controller=r["controller_name"],**p) for r in records for p in r["summary"]["internal"]["poles"]])
        write_csv(out/"crossovers.csv",[dict(controller=r["controller_name"],**p) for r in records for p in r["summary"]["crossovers"]])
        if should_cancel and should_cancel():raise Cancelled("频域报告保存前已取消")
        if plots:
            from .frequency_plots import build
            build(out,records)
        images="".join('<img width="100%" src="figures/'+p.name+'">' for p in sorted((out/"figures").glob("*.png")))
        (out/"report.html").write_text('<!doctype html><meta charset="utf-8"><h1>采样反馈环路分析</h1><p>有限频段 · 未饱和线性分支 · 合成模型。正裕度不代替内部稳定性或压力测试。</p><p><a href="summary.json">指标、全部检出交越与计算状态</a> · <a href="config.json">冻结配置</a> · <a href="poles.csv">内部极点</a></p><pre>'+html.escape(json.dumps([r["summary"] for r in records],indent=2,ensure_ascii=False))+'</pre>'+images,encoding="utf-8")
        failed=sum(r["metrics"]["status"]!="completed" for r in records);artifacts.finish(out,manifest,records,failed)
        return out/"report.html",failed
    except BaseException as exc:
        artifacts.interrupted(out,manifest,records,0,exc);raise

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--config",type=Path);parser.add_argument("--output",type=Path,required=True);parser.add_argument("--plots",action="store_true")
    args=parser.parse_args();value=json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else default_config()
    report,failed=execute(args.output,value,plots=args.plots);print(report)
    if failed:parser.exit(1)
if __name__=="__main__":main()

