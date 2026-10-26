"""Saved open-loop previews for explicitly defined custom LTI models."""
import csv
import html
import math
from pathlib import Path
from . import analysis_artifacts as artifacts
from .experiment import Cancelled, atomic_json, keys
from .linear_models import TransferFunctionPlant, snapshot, validate_plant


def validate_config(value):
    keys(value, ("plant","dt_s","duration_s"), "模型预览")
    p=validate_plant(value["plant"])
    dt,duration=value["dt_s"],value["duration_s"]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in (dt,duration)):
        raise ValueError("预览采样周期与时长须为正")
    count=duration/dt
    if not math.isfinite(count) or not 1 <= count <= 5000 or not math.isclose(count,round(count),rel_tol=0,abs_tol=1e-8):
        raise ValueError("开环预览需要1～5000个完整采样区间")
    snapshot(p,dt)
    return dict(plant=p,dt_s=dt,duration_s=duration)


def execute(output,value,*,plots=True,progress=None,should_cancel=None):
    c=validate_config(value);out,manifest=artifacts.begin(output,"model-preview-1.0",c,1)
    rows=[]
    try:
        atomic_json(out/"config.json",c);atomic_json(out/"model-snapshot.json",snapshot(c["plant"],c["dt_s"]))
        plant=TransferFunctionPlant(**c["plant"])
        for i in range(round(c["duration_s"]/c["dt_s"])+1):
            if should_cancel and should_cancel():raise Cancelled("模型预览已取消")
            rows.append(dict(time_s=i*c["dt_s"],input=1.0,disturbance=0.0,output=plant.output))
            if abs(plant.output)>1e8:raise ValueError("开环输出超过预览观察范围1e8；不能据此判定闭环性质")
            if i < round(c["duration_s"]/c["dt_s"]):plant.advance(1.0,0.0,c["dt_s"])
        with (out/"preview.csv").open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        if plots:
            from matplotlib.figure import Figure
            fig=Figure(figsize=(11,5),layout="constrained");ax=fig.add_subplot()
            ax.plot([r["time_s"] for r in rows],[r["output"] for r in rows])
            ax.set(xlabel="Time / s",ylabel="Output / "+c["plant"]["units"]["output"],title="Open-loop unit step | synthetic LTI")
            ax.grid(alpha=.2);(out/"figures").mkdir()
            for suffix in ("png","svg"):fig.savefig(out/"figures"/("open-loop."+suffix),dpi=150)
        image = '<p><img width="100%" src="figures/open-loop.png"></p>' if plots else ""
        (out/"report.html").write_text('<!doctype html><meta charset="utf-8"><h1>'+html.escape(c["plant"]["name"])+'</h1><p>合成线性对象的开环单位阶跃预览，不是闭环稳定性证明。</p><a href="model-snapshot.json">冻结模型与采样矩阵</a> · <a href="preview.csv">完整数据</a>'+image,encoding="utf-8")
        records=[dict(case_id="open_loop",metrics=dict(status="completed"),samples=len(rows),model_snapshot="model-snapshot.json")]
        artifacts.finish(out,manifest,records,0)
        return out/"report.html",0
    except BaseException as exc:
        if rows:
            atomic_json(out/"partial-preview.json",rows)
        artifacts.interrupted(out,manifest,[],1,exc)
        raise



def main():
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,help="JSON with plant, dt_s and duration_s")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--plots",action="store_true")
    args=parser.parse_args()
    from .linear_models import default_plant
    value=json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else dict(plant=default_plant(),dt_s=.01,duration_s=12.)
    report,failed=execute(args.output,value,plots=args.plots)
    print(report)
    if failed:parser.exit(1)


if __name__=="__main__":main()
