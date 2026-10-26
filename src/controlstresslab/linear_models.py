"""Explicit two-input, one-output continuous LTI models (orders 1..4).

Observable companion states retain the declared order, including hidden modes.
Discretization uses an augmented matrix exponential, so integrators need no A^-1.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math

MODEL = "transfer_function"
MAX_ORDER = 4


def default_plant():
    return dict(name="自定义一阶对象", numerator=[1.0], denominator=[1.0, 1.0],
        disturbance_numerator=[1.0], initial_state=[0.0], gain_scale=1.0, time_scale=1.0,
        units=dict(input="unit", output="unit", disturbance="unit"))


def _trimmed(values):
    first=0
    while first<len(values)-1 and values[first]==0:first+=1
    return values[first:]


def validate_plant(value):
    if not isinstance(value, dict) or set(value) != set(default_plant()):
        raise ValueError("传递函数对象字段不匹配")
    p = deepcopy(value)
    for key in ("name",):
        if not isinstance(p[key], str) or not p[key].strip() or len(p[key]) > 120:
            raise ValueError("模型名称需要1～120个字符")
    for key in ("numerator", "denominator", "initial_state"):
        v = p[key]
        if not isinstance(v, list) or not v or any(type(x) not in (int,float) or not math.isfinite(x) for x in v):
            raise ValueError(key+"须为非空有限实数数组")
    den = p["denominator"]
    n = len(den)-1
    if not 1 <= n <= MAX_ORDER or den[0] == 0:
        raise ValueError("分母需为1～4阶，首项不能为零，系数按降幂排列")
    if len(_trimmed(p["numerator"])) > n:
        raise ValueError("只支持严格真有理对象：分子阶数必须小于分母阶数")
    d = p["disturbance_numerator"]
    if d is not None and (not isinstance(d,list) or not d or len(_trimmed(d)) > n or
            any(type(x) not in (int,float) or not math.isfinite(x) for x in d)):
        raise ValueError("扰动分子须为严格真有理的有限系数数组，或null表示不提供通道")
    if len(p["initial_state"]) != n:
        raise ValueError("初始状态数量须等于分母阶数（可观测标准型）")
    for key in ("gain_scale","time_scale"):
        if type(p[key]) not in (int,float) or not math.isfinite(p[key]) or abs(p[key]) > 1e6:
            raise ValueError(key+"须为±1000000内的有限实数")
    if p["time_scale"] <= 0: raise ValueError("时间尺度须为正")
    if not isinstance(p["units"],dict) or set(p["units"]) != {"input","output","disturbance"}:
        raise ValueError("需要分别声明输入、输出、扰动单位")
    for v in p["units"].values():
        if not isinstance(v,str) or not v.strip() or len(v) > 40: raise ValueError("单位需为1～40个字符")
    coeff = p["numerator"] + den + (d or [0])
    if any(abs(v/den[0]) > 1e8 or not math.isfinite(v/den[0]) for v in coeff):
        raise ValueError("归一化系数超过当前数值范围±1e8")
    return p


def continuous(value):
    p = validate_plant(value)
    den=p["denominator"];n=len(den)-1;lead=den[0];tau=p["time_scale"]
    # Transpose of controller companion form: C = [1,0,...].
    a=[[0.0]*n for _ in range(n)]
    for i in range(n):
        a[i][0]=-den[i+1]/lead/tau
        if i+1 < n:a[i][i+1]=1.0/tau
    def channel(num,scale):
        num=_trimmed(num)
        padded=[0.0]*(n-len(num))+num
        return [v/lead*scale/tau for v in padded]
    bu=channel(p["numerator"],p["gain_scale"])
    bd=channel(p["disturbance_numerator"] or [0.0],1.0)
    return a,[[u,d] for u,d in zip(bu,bd)],[[1.0]+[0.0]*(n-1)],[[0.0,0.0]]


@lru_cache(maxsize=256)
def _sampled(raw,dt):
    try:
        import numpy as np
        from scipy.linalg import expm
    except ImportError as exc:
        raise ImportError("通用模型需要数值依赖，请安装 controlstresslab[analysis] 或 [gui]") from exc
    p=json.loads(raw);a,b,c,d=continuous(p);n=len(a)
    aug=np.zeros((n+2,n+2));aug[:n,:n]=a;aug[:n,n:]=b
    with np.errstate(over="raise",invalid="raise"):
        transition=expm(aug*dt)
    if not np.isfinite(transition).all():raise ValueError("采样矩阵非有限，请核对系数与采样周期")
    ad=transition[:n,:n].copy();bd=transition[:n,n:].copy()
    ad.flags.writeable=False;bd.flags.writeable=False
    return ad,bd


def sampled(value,dt):
    p=validate_plant(value)
    if type(dt) not in (int,float) or not math.isfinite(dt) or dt <= 0:raise ValueError("采样周期须为正")
    return _sampled(json.dumps(p,sort_keys=True,ensure_ascii=False,allow_nan=False),float(dt))


def snapshot(value,dt):
    import numpy as np
    import scipy
    p=validate_plant(value);a,b,c,d=continuous(p);ad,bd=sampled(p,dt)
    raw=json.dumps(p,sort_keys=True,ensure_ascii=False,allow_nan=False).encode("utf-8")
    poles=np.linalg.eigvals(a)
    return dict(schema="lti-snapshot-1.0",model=MODEL,definition=p,definition_sha256=hashlib.sha256(raw).hexdigest(),
        state_basis="observable_companion; output=x[0]; no pole-zero cancellation",
        continuous=dict(A=a,B=b,C=c,D=d),sampled=dict(A=ad.tolist(),B=bd.tolist(),C=c,D=d,dt_s=dt,method="augmented_expm_zoh"),
        poles=[dict(real=float(z.real),imag=float(z.imag)) for z in poles],
        software=dict(numpy=np.__version__,scipy=scipy.__version__),
        scope="synthetic finite-order LTI; no robust stability or hardware claim")


class TransferFunctionPlant:
    def __init__(self,**kwargs):
        self._definition=validate_plant(kwargs or default_plant())
        self.reset()

    @property
    def definition(self):return deepcopy(self._definition)

    def to_config(self):return deepcopy(self._definition)

    def reset(self):
        self.state=list(self._definition["initial_state"]);self.output=float(self.state[0])
        self._dt=None;self._matrices=None

    def advance(self,u,disturbance,dt):
        import numpy as np
        if not all(math.isfinite(v) for v in (u,disturbance)):raise ValueError("对象输入必须有限")
        if self._definition["disturbance_numerator"] is None and disturbance != 0:
            raise ValueError("此对象没有声明扰动通道")
        if type(dt) not in (int,float) or not math.isfinite(dt) or dt <= 0:raise ValueError("采样周期须为正")
        if self._dt != dt:
            self._matrices=sampled(self._definition,dt);self._dt=dt
        a,b=self._matrices
        with np.errstate(over="raise",invalid="raise"):
            next_state=a@self.state+b@np.array([u,disturbance])
        if not np.isfinite(next_state).all():raise ValueError("状态发生数值溢出")
        self.state=next_state.tolist();self.output=float(self.state[0])


def template(model,plant=None):
    """Zero-state equivalents; physical initial-state conversion is explicit."""
    p=default_plant()
    if model=="first_order":
        v=plant or dict(gain=1.0,tau_s=1.0,initial_output=0.0)
        p.update(name="一阶等效传递函数",numerator=[v["gain"]],denominator=[v["tau_s"],1.0],
                 disturbance_numerator=[1.0],initial_state=[v["initial_output"]])
    elif model=="second_order":
        v=plant or dict(mass_kg=1.0,damping_N_s_m=.6,stiffness_N_m=4.0,initial_output=0.0,initial_velocity_m_s=0.0)
        p.update(name="二阶等效传递函数",numerator=[1.0],denominator=[v["mass_kg"],v["damping_N_s_m"],v["stiffness_N_m"]],
                 disturbance_numerator=[1.0],initial_state=[v["initial_output"],v["initial_velocity_m_s"]+v["damping_N_s_m"]/v["mass_kg"]*v["initial_output"]],
                 units=dict(input="N",output="m",disturbance="N"))
    elif model=="integrator":
        p.update(name="积分对象",denominator=[1.0,0.0])
    elif model=="fourth_order":
        p.update(name="四阶惯性对象",denominator=[1.,10.,35.,50.,24.],numerator=[24.],disturbance_numerator=[1.],initial_state=[0.]*4)
    else:raise ValueError("未知模型模板")
    return validate_plant(p)


def save_snapshot(output, config):
    """Content-addressed model snapshots; callers add the reference to each run."""
    if config["model"] != MODEL:return {}
    from .experiment import atomic_json, sha
    value=snapshot(config["plant"],config["conditions"]["dt_s"])
    identity=hashlib.sha256(json.dumps(dict(definition=value["definition"],dt=value["sampled"]["dt_s"]),
        sort_keys=True,ensure_ascii=False,allow_nan=False).encode("utf-8")).hexdigest()
    folder=output/"models";folder.mkdir(exist_ok=True)
    name="models/"+identity+".json";path=output/name
    if not path.exists():atomic_json(path,value)
    return dict(model_snapshot=name,model_snapshot_sha256=sha(path))
