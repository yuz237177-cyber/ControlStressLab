"""Predeclared finite tuning plans. This module never reads simulation results."""
from copy import deepcopy
import hashlib
import itertools
import json
import math

from .benchmark_design import controller_for
from .experiment import default_config as experiment_config, finite_tree, keys, scenario_for, validate_config as validate_experiment
from .robustness import allowed_axes

STRUCTURES = ("PI", "PID_aw", "TwoDOF_PID")
THRESHOLDS = {"error_max": "normalized_rmse", "saturation_max": "saturation_fraction", "variation_max": "input_variation_rate"}
MAX_RUNS, MAX_INTERVALS = 1000, 2_000_000


def digest(value):
    # Numeric spelling and incidental seed/filename labels are not new stimuli.
    def normalize(v):
        if type(v) in (int, float): return float(v)
        if isinstance(v, dict): return {k: normalize(x) for k, x in v.items()}
        if isinstance(v, list): return [normalize(x) for x in v]
        return v
    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def baseline(config):
    return deepcopy(next(c["parameters"] for c in config["base"]["controllers"] if c["name"] == config["controller"]))


def templates(base, validation=False):
    r = base["conditions"]["reference_scale"]
    start = .7 if validation else .5
    ref = {**base["reference"], "kind": "step", "start_s": start, "offset": 0., "amplitude": (.8 if validation else 1.)*r}
    zero = {**base["disturbance"], "kind": "constant", "offset": 0., "amplitude": 0.}
    periodic = {**ref, "kind": "chirp" if validation else "sine", "offset": (.55 if validation else .6)*r,
                "amplitude": (.25 if validation else .3)*r, "frequency_hz": .17 if validation else .29, "stop_frequency_hz": .73}
    load = {**zero, "kind": "prbs" if validation else "step", "amplitude": (.18 if validation else .2) if base["model"] == "first_order" else (.45 if validation else .5),
            "start_s": 6., "hold_s": .3}
    families = [dict(id=name, reference=reference, disturbance=disturbance,
                 conditions=dict(evaluation_start_s=evaluation, recovery_start_s=evaluation, recovery_mode="tracking_only"))
            for name, reference, disturbance, evaluation in (("step", ref, zero, start), ("tracking", periodic, zero, start), ("disturbance", ref, load, 6.))]
    if base["model"] == "transfer_function" and base["plant"]["disturbance_numerator"] is None:
        families = [f for f in families if f["id"] != "disturbance"]
    return families


def default_config(base=None, controller="PID_aw"):
    provided = base is not None
    base = deepcopy(base) if provided else experiment_config()
    if not provided: base["conditions"]["noise_std"] = .01*base["conditions"]["reference_scale"]
    base["selected_controllers"] = [controller]
    key = "plant.time_scale" if base["model"] == "transfer_function" else "plant.tau_s" if base["model"] == "first_order" else "plant.mass_kg"
    nominal = base["plant"][key.split(".")[1]]
    bounds = dict(kp=(.3,6), ki=(.1,6), kd=(.002,.6)) if base["model"] == "first_order" else dict(kp=(1,20),ki=(.2,8),kd=(.2,8))
    names = ("kp", "ki") if controller == "PI" else ("kp", "ki", "kd")
    ranges = {k:dict(low=bounds[k][0],high=bounds[k][1],scale="log") for k in names}
    if controller == "TwoDOF_PID": ranges["beta"] = dict(low=.3,high=1.,scale="linear")
    two = base["conditions"]["noise_std"] > 0
    return dict(schema="tuning-config-1.0", base=base, controller=controller, candidate_budget=32, search_seed=91731,
        ranges=ranges, thresholds=dict(error_max=None,saturation_max=.25,variation_max=None),
        search=dict(axes=[dict(key=key,values=[.8*nominal,1.2*nominal]),dict(key="conditions.measurement_delay_s",values=[0.,.04])],
                    families=templates(base), seeds=[81011,81012] if two else [81011]),
        validation=dict(points=[{key:a*nominal,"conditions.measurement_delay_s":b} for a,b in ((.9,.01),(1.,.03),(1.1,.05),(1.35,.02),(.7,.06))],
                        families=templates(base,True), seeds=[82011,82012] if two else [82011], waveform_seeds=[83011,83012] if two else [83011]),
        max_runs=1000,max_intervals=2_000_000,observed_inputs=[])


def candidates(config):
    original = baseline(config)
    unique, aliases, seen = [], [], {}
    for index in range(config["candidate_budget"]):
        params = deepcopy(original)
        if index:
            for name, r in config["ranges"].items():
                u = (int.from_bytes(hashlib.sha256(f"{config['search_seed']}|{index}|{name}".encode()).digest()[:8],"big") >> 11)/2**53
                a,b = r["low"],r["high"]
                params[name] = a if a == b else (a+(b-a)*u if r["scale"] == "linear" else math.exp(math.log(a)+(math.log(b)-math.log(a))*u))
        controller_for(config["controller"],params)
        signature = digest(params)
        if signature in seen:
            aliases.append(dict(requested_id=index,candidate_id=seen[signature]))
        else:
            seen[signature] = index
            unique.append(dict(candidate_id=index,parameters=params,baseline=index==0))
    return unique, aliases


def input_payload(value):
    s = scenario_for(value)
    plant = deepcopy(value["plant"])
    if value["model"] == "transfer_function":
        from .linear_models import continuous
        a,b,c,d=continuous(plant)
        plant=dict(A=a,B=b,C=c,D=d,initial_state=plant["initial_state"])
    return dict(model=value["model"],plant=plant,dt_s=s.dt_s,duration_s=s.duration_s,
                input_limit=s.voltage_limit,measurement_delay_s=s.measurement_delay_s,
                reference=s.reference.values,disturbance=s.load.values,noise=s.noise_sequence())


def _integer(v, low, high, title):
    if type(v) is not int or not low <= v <= high: raise ValueError(title+f"须为{low}～{high}整数")


def _seeds(values, title):
    if not isinstance(values,list) or not 1 <= len(values) <= 10: raise ValueError(title+"需要1～10个种子")
    for v in values: _integer(v,0,2**32-1,title)
    if len(set(values)) != len(values): raise ValueError(title+"不能重复")


def prepare(value):
    finite_tree(value)
    keys(value,default_config(),"约束整定")
    c = deepcopy(value)
    if c["schema"] != "tuning-config-1.0": raise ValueError("未知整定协议")
    c["base"] = validate_experiment(c["base"])
    if c["controller"] not in STRUCTURES: raise ValueError("本模式支持PI、PID_aw、TwoDOF_PID")
    if c["base"]["selected_controllers"] != [c["controller"]]: raise ValueError("一个任务只选择一种控制器结构")
    _integer(c["candidate_budget"],2,128,"候选预算")
    _integer(c["search_seed"],0,2**32-1,"搜索种子")
    _integer(c["max_runs"],1,MAX_RUNS,"总运行预算")
    _integer(c["max_intervals"],1,MAX_INTERVALS,"总推进区间预算")
    names = {"kp","ki"} if c["controller"] == "PI" else {"kp","ki","kd"}
    if c["controller"] == "TwoDOF_PID": names.add("beta")
    if not isinstance(c["ranges"],dict) or not c["ranges"] or set(c["ranges"])-names: raise ValueError("搜索参数与控制器结构不匹配")
    for name,r in c["ranges"].items():
        keys(r,("low","high","scale"),"搜索范围")
        if any(type(r[k]) not in (int,float) for k in ("low","high")) or not 0 <= r["low"] <= r["high"]: raise ValueError("范围需非负且下限≤上限")
        if r["scale"] not in ("linear","log") or r["scale"] == "log" and r["low"] <= 0: raise ValueError("对数范围必须严格为正")
        if name == "beta" and (r["scale"] != "linear" or r["high"] > 1): raise ValueError("beta须在线性尺度[0,1]内")
    keys(c["thresholds"],THRESHOLDS,"要求")
    if all(v is None for v in c["thresholds"].values()): raise ValueError("至少启用一项要求")
    for k,v in c["thresholds"].items():
        if v is not None and (type(v) not in (int,float) or v < 0 or k == "saturation_max" and v > 1): raise ValueError("要求阈值无效")
    if not isinstance(c["observed_inputs"],list) or any(not isinstance(h,str) or len(h)!=64 or any(x not in "0123456789abcdef" for x in h) for h in c["observed_inputs"]): raise ValueError("已观察输入指纹无效")
    keys(c["search"],("axes","families","seeds"),"搜索工况")
    keys(c["validation"],("points","families","seeds","waveform_seeds"),"验证工况")
    axes = c["search"]["axes"]
    if not isinstance(axes,list) or not 1 <= len(axes) <= 2: raise ValueError("使用1～2条工况轴")
    axis_names = []
    for axis in axes:
        keys(axis,("key","values"),"工况轴")
        if axis["key"] not in allowed_axes(c["base"]["model"]): raise ValueError("工况轴与对象不匹配")
        values = axis["values"]
        if not isinstance(values,list) or not 1 <= len(values) <= 21 or any(type(v) not in (float,int) for v in values) or any(a>=b for a,b in zip(values,values[1:])): raise ValueError("轴需要1～21个严格递增实数")
        axis_names.append(axis["key"])
    if len(set(axis_names)) != len(axis_names): raise ValueError("工况轴不能重复")
    points = c["validation"]["points"]
    if not isinstance(points,list) or not 1 <= len(points) <= 64: raise ValueError("验证需1～64个明确条件")
    for p in points:
        keys(p,axis_names,"验证条件")
        if any(type(v) not in (int,float) for v in p.values()): raise ValueError("验证轴值须为实数")
    proposed, aliases = candidates(c)
    for stage in ("search","validation"):
        spec = c[stage]
        _seeds(spec["seeds"],"噪声种子")
        if stage == "validation":
            _seeds(spec["waveform_seeds"],"验证波形种子")
            if len(spec["waveform_seeds"]) != len(spec["seeds"]): raise ValueError("验证噪声/波形种子按索引一一配对")
        families = spec["families"]
        if not isinstance(families,list) or not 1 <= len(families) <= 6: raise ValueError("每阶段需1～6个信号族")
        ids = []
        for family in families:
            keys(family,("id","reference","disturbance","conditions"),"信号族")
            name = family["id"]
            if not isinstance(name,str) or not name or len(name)>40 or not name.isascii() or not all(x.isalnum() or x in "_-" for x in name): raise ValueError("信号族ID使用1～40位英文、数字、下划线")
            ids.append(name)
            if not isinstance(family["conditions"],dict) or set(family["conditions"])-{"evaluation_start_s","recovery_start_s","recovery_mode","recovery_band","recovery_dwell_s"}: raise ValueError("信号族仅可改变评价/恢复条件")
        if len(set(ids)) != len(ids): raise ValueError("信号族ID不能重复")
    n = math.prod(len(a["values"]) for a in axes)*len(c["search"]["families"])*len(c["search"]["seeds"])
    m = len(points)*len(c["validation"]["families"])*len(c["validation"]["seeds"])
    count = len(proposed)*n+3*m
    intervals = round(c["base"]["conditions"]["duration_s"]/c["base"]["conditions"]["dt_s"])
    if count > c["max_runs"] or count*intervals > c["max_intervals"]: raise ValueError(f"计划上限{count}次/{count*intervals}个推进区间，超过声明预算")
    seen = set()
    plans = {}
    for stage in ("search","validation"):
        stage_points = [dict(zip(axis_names,v)) for v in itertools.product(*(a["values"] for a in axes))] if stage == "search" else points
        cases = []
        for fi,family in enumerate(c[stage]["families"]):
            for pi,point in enumerate(stage_points):
                for si,seed in enumerate(c[stage]["seeds"]):
                    v = deepcopy(c["base"])
                    v["reference"],v["disturbance"] = deepcopy(family["reference"]),deepcopy(family["disturbance"])
                    v["conditions"].update(family["conditions"],seed=seed)
                    if stage == "validation": v["disturbance"]["seed"] = c[stage]["waveform_seeds"][si]
                    for k,level in point.items():
                        group,field = k.split(".")
                        if k == "disturbance.amplitude" and v["disturbance"]["kind"] == "constant": raise ValueError("常值扰动不使用幅值轴，请使用有效波形")
                        v[group][field] = level
                    v = validate_experiment(v)
                    payload = input_payload(v)
                    signature = digest(payload)
                    if signature in seen: raise ValueError("发现重复输入工况（包括换ID/零噪声换种子）；请使用唯一条件")
                    if stage == "validation" and signature in c["observed_inputs"]: raise ValueError("验证包含已观察输入，不能称为新工况")
                    seen.add(signature)
                    contract = dict(evaluation_start_s=v["conditions"]["evaluation_start_s"],reference_scale=v["conditions"]["reference_scale"],
                                    recovery={k:x for k,x in v["conditions"].items() if k.startswith("recovery_")})
                    cases.append(dict(case_id=f"{stage}_f{fi}_p{pi}_s{si}",family=family["id"],condition_index=pi,input_index=si,
                                      seed=seed,point=point,run_config=v,input_sha256=signature,contract_sha256=digest(contract)))
        plans[stage] = cases
    original=baseline(c)
    outside=[name for name,r in c["ranges"].items() if not r["low"]<=original[name]<=r["high"]]
    return dict(config=c,candidates=proposed,aliases=aliases,warnings=(["基线参数不在搜索范围内，仍保留原值："+", ".join(outside)] if outside else []),**plans,
                budget=dict(unique_candidates=len(proposed),search_runs=len(proposed)*n,validation_reserved=3*m,total_upper=count,intervals_upper=count*intervals))


def validate_config(value):
    return prepare(value)["config"]
