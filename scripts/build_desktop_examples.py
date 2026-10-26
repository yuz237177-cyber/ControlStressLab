"""Build complete synthetic example projects with real saved phase results."""
from copy import deepcopy
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from controlstresslab import projects,robustness,tuning,tuning_protocol,tuning_validation,frequency
from controlstresslab.experiment import default_config,execute,atomic_json
from controlstresslab.linear_models import template
def build(output,examples):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False);examples=Path(examples).resolve();examples.mkdir(exist_ok=True)
    details=[]
    for key,model,title in (("first-order","first_order","一阶过程：参数与延迟"),("second-order","second_order","二阶振荡：误差与动作"),("custom","transfer_function","自定义四阶：建模到冻结验证")):
        c=default_config(model);c["name"]=title
        if model=="transfer_function":c["plant"]=template("fourth_order")
        c["selected_controllers"]=["PI","PID_aw","TwoDOF_PID"];c["conditions"].update(dt_s=.02,noise_std=.005,measurement_delay_s=.02)
        for d in c["controllers"]:
            if d["name"]!="LADRC":
                d["parameters"].update(kp=.5 if model=="transfer_function" else 1.,ki=.2 if model=="transfer_function" else .5)
                if d["name"]!="PI":d["parameters"]["kd"]=.2
        project=projects.create(output/key,title,c,"合成模型上的完整示例；先声明要求，再用搜索选择，冻结后检查未参与选择的工况。")
        execute(project/"results/01-experiment",c,plots=True);projects.register(project,project/"results/01-experiment")
        scan=robustness.default_config(c);axis=scan["axes"][0]["key"]
        scan["axes"][0]["values"]=[.8,1.,1.2];scan["axes"][1]["values"]=[0.,.04]
        robustness.execute(project/"results/02-scan",scan,plots=True);projects.register(project,project/"results/02-scan")
        tc=tuning_protocol.default_config(c);tc["candidate_budget"]=4
        tc["ranges"]=dict(kp=dict(low=.3,high=.8 if model=="transfer_function" else 1.5,scale="linear"),
            ki=dict(low=.05,high=.3 if model=="transfer_function" else .8,scale="linear"),kd=dict(low=.05,high=.3,scale="linear"))
        tc["thresholds"]=dict(error_max=1.5,saturation_max=.8,variation_max=10.)
        tc["search"]["axes"]=tc["search"]["axes"][:1];tc["search"]["families"]=tc["search"]["families"][:2];tc["search"]["seeds"]=[81011]
        tc["validation"]["points"]=[{axis:.9},{axis:1.1}];tc["validation"]["families"]=tc["validation"]["families"][:2]
        tc["validation"]["seeds"]=[82011];tc["validation"]["waveform_seeds"]=[83011]
        projects.update_draft(project,tc)
        tuning.execute(project/"results/03-search",tc,plots=True);projects.register(project,project/"results/03-search")
        summary=json.loads((project/"results/03-search/summary.json").read_text(encoding="utf-8"))
        main=summary["low_error_id"]
        if main is None:raise ValueError("示例无可行候选："+key)
        tuning_validation.freeze(project/"results/04-selection",dict(search_folder=str(project/"results/03-search"),candidate_ids=[main],main_candidate_id=main,
            rationale="从已保存搜索中选择误差目标较低的可行候选；保持参数冻结，独立验证不重新选参。"))
        projects.register(project,project/"results/04-selection")
        tuning_validation.execute(project/"results/05-validation",dict(selection_folder=str(project/"results/04-selection")),plots=True);projects.register(project,project/"results/05-validation")
        frequency.execute(project/"results/06-frequency",frequency.default_config(c),plots=True);projects.register(project,project/"results/06-frequency")
        projects.export_bundle(project,examples/(key+".cslproj"));details.append(dict(example=key,folder=str(project),main=main))
        print("Example complete:",key,flush=True)
    atomic_json(output/"example-build.json",details)
if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--examples",type=Path,default=ROOT/"examples")
    args=parser.parse_args();build(args.output,args.examples)
