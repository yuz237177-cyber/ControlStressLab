"""Checks against the original nonlinear simulator and PID objects."""
from copy import deepcopy
import math
import numpy as np
from .benchmark_design import controller_for
from .experiment import plant_for_config,scenario_for
from .simulation import simulate
from .frequency_model import response

def consistency(base,model,folder,should_cancel=None):
    from .cli import write_csv
    from .experiment import Cancelled
    c=deepcopy(base);dt=model["dt_s"]
    if c["model"]=="transfer_function":c["plant"]["initial_state"]=[0.]*(len(c["plant"]["denominator"])-1)
    else:
        c["plant"]["initial_output"]=0.
        if "initial_velocity_m_s" in c["plant"]:c["plant"]["initial_velocity_m_s"]=0.
    intervals=min(600,round(c["conditions"]["duration_s"]/dt))
    if intervals<4:return dict(state="not_applicable",reason="核对窗口不足"),[]
    c["conditions"].update(duration_s=intervals*dt,noise_std=0,evaluation_start_s=2*dt,recovery_start_s=2*dt,
        recovery_dwell_s=dt,recovery_mode="tracking_only")
    c["reference"].update(kind="step",offset=0.,start_s=2*dt)
    c["disturbance"].update(kind="constant",amplitude=0.,offset=0.,start_s=0.)
    params=model["parameters"]
    a,b,co,di=(np.array(model["closed"][key]) for key in ("A","B","C","D"))
    for attempt in range(9):
        if should_cancel and should_cancel():raise Cancelled("频域时域核对已取消")
        amp=.01*c["conditions"]["reference_scale"]*10**-attempt;c["reference"]["amplitude"]=amp
        scenario=scenario_for(c);run=simulate(plant_for_config(c),controller_for(model["controller"],params),scenario)
        if run.status!="completed" or any(row["command_V"] is not None and row["command_V"]!=row["applied_V"] for row in run.rows):continue
        x=np.zeros(len(a));rows=[]
        for i,row in enumerate(run.rows):
            inputs=np.array([row["reference_rad_s"],0.,0.]);y,u=co@x+di@inputs
            actual_u=row["applied_V"]
            rows.append(dict(time_s=i*dt,simulated_y=row["true_output_rad_s"],linear_y=float(y),
                simulated_u=actual_u,linear_u=float(u) if actual_u is not None else None,
                output_error=abs(float(y)-row["true_output_rad_s"]),input_error=abs(float(u)-actual_u) if actual_u is not None else None))
            x=a@x+b@inputs
        write_csv(folder/"step.csv",rows)
        passed=all(np.isclose(r["simulated_y"],r["linear_y"],atol=1e-9,rtol=1e-7) and
            (r["simulated_u"] is None or np.isclose(r["simulated_u"],r["linear_u"],atol=1e-9,rtol=1e-7)) for r in rows)
        return dict(state="passed" if passed else "failed",amplitude=amp,scaling_attempt=attempt,steps=intervals,
            max_output_error=max(r["output_error"] for r in rows),max_input_error=max(r["input_error"] or 0 for r in rows),
            atol=1e-9,rtol=1e-7,terminal_action_absent=rows[-1]["simulated_u"] is None),c
    return dict(state="not_applicable",reason="9级缩小后仍失败或饱和；未更改原实验"),c

def sine_check(base,model,poles,folder,should_cancel=None):
    from .cli import write_csv
    from .experiment import Cancelled
    if poles["state"]!="stable":return dict(state="not_applicable",reason="标称内部环路非严格稳定")
    rho=poles["spectral_radius"];dt=model["dt_s"];period=max(24,round(2*math.pi/dt))
    warm=max(period,math.ceil(math.log(1e-8)/math.log(rho))) if 0<rho<1 else period
    count=warm+3*period
    if count>16000:return dict(state="not_applicable",reason="正弦预热超过16000拍预算")
    c=deepcopy(base)
    if c["model"]=="transfer_function":c["plant"]["initial_state"]=[0.]*(len(c["plant"]["denominator"])-1)
    else:
        c["plant"]["initial_output"]=0.
        if "initial_velocity_m_s" in c["plant"]:c["plant"]["initial_velocity_m_s"]=0.
    plant=plant_for_config(c);controller=controller_for(model["controller"],model["parameters"])
    w=2*math.pi/(period*dt);amp=.001*c["conditions"]["reference_scale"];rows=[]
    limit=c["conditions"]["input_limit"]
    for k in range(count):
        if k%128==0 and should_cancel and should_cancel():raise Cancelled("正弦核对已取消")
        t=k*dt;r=amp*math.sin(w*t)
        # Match measurement delay using the true-output history, as in simulate().
        measured=rows[k-model["delay_samples"]]["output"] if k>=model["delay_samples"] and model["delay_samples"] else plant.output if model["delay_samples"]==0 else 0.
        request=controller.command(r,measured,dt)
        if not math.isfinite(request) or abs(request)>=limit:return dict(state="not_applicable",reason="正弦核对触发限幅")
        rows.append(dict(time_s=t,reference=r,output=plant.output,input=request))
        controller.observe_applied(request);plant.advance(request,0.,dt)
        if not math.isfinite(plant.output) or abs(plant.output)>c["conditions"]["output_bound"]:return dict(state="not_applicable",reason="正弦核对超出观察范围")
    tail=rows[warm:];t=np.array([r["time_s"] for r in tail]);design=np.column_stack((np.sin(w*t),np.cos(w*t),np.ones(len(t))))
    fit=np.linalg.lstsq(design,np.array([r["output"] for r in tail]),rcond=None)[0]
    measured=complex(fit[0],fit[1])/amp;expected=response(model,[w])["Y_R"][0]
    error=float(abs(measured-expected));tolerance=1e-4*(1+abs(expected))
    write_csv(folder/"sine.csv",rows)
    return dict(state="passed" if error<=tolerance else "failed",omega_rad_s=w,warmup_samples=warm,measured_samples=len(tail),
        measured=dict(real=measured.real,imag=measured.imag),expected=dict(real=float(expected.real),imag=float(expected.imag)),
        abs_error=error,tolerance=float(tolerance))

