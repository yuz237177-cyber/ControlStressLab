"""Uncancelled sampled PID feedback model; measurement delay stays in feedback."""
from copy import deepcopy
import math
import numpy as np
from .experiment import validate_config
from .linear_models import continuous,sampled,template

SUPPORTED=("PI","PID_aw","TwoDOF_PID")
COMPILER="sampled-pid-1.0"

def compile_model(base,name):
    base=validate_config(base)
    if name not in SUPPORTED:raise ValueError("频域仅支持PI/PID族，LADRC未建立对应模型")
    p=base["plant"] if base["model"]=="transfer_function" else template(base["model"],base["plant"])
    ad,bd=sampled(p,base["conditions"]["dt_s"]);_,_,c,_=continuous(p)
    c=np.array(c)[0];n=len(ad);dt=base["conditions"]["dt_s"]
    delay=round(base["conditions"]["measurement_delay_s"]/dt)
    if delay>128:raise ValueError("频域测量延迟最多128拍；时域实验仍可使用原有范围")
    params=deepcopy(next(d["parameters"] for d in base["controllers"] if d["name"]==name))
    kp,ki,kd=(params[k] for k in ("kp","ki","kd"))
    alpha=math.exp(-dt/params["derivative_filter_s"]) if params["derivative_filter_s"] else 0.
    labels=(["integral"] if ki else [])+(["previous_measurement"] if kd else [])+(["filtered_derivative"] if kd and alpha else [])
    m=len(labels);ac=np.zeros((m,m));br=np.zeros(m);bm=np.zeros(m);cu=np.zeros(m)
    if ki:
        i=labels.index("integral");ac[i,i]=1; br[i]=ki*dt;bm[i]=-ki*dt;cu[i]=1
    if kd:
        i=labels.index("previous_measurement");bm[i]=1;cu[i]=kd*(1-alpha)/dt
        if alpha:
            j=labels.index("filtered_derivative");ac[j,j]=alpha;ac[j,i]=-(1-alpha)/dt
            bm[j]=(1-alpha)/dt;cu[j]=-kd*alpha
    dr=kp*params.get("beta",1.)+ki*dt
    dm=-kp-ki*dt-kd*(1-alpha)/dt
    size=n+m+delay;measure=np.zeros(size)
    if delay:measure[n+m]=1.
    else:measure[:n]=c
    ur=dm*measure;ur[n:n+m]+=cu
    a=np.zeros((size,size));b=np.zeros((size,3))
    a[:n,:n]=ad;a[:n,:]+=np.outer(bd[:,0],ur)
    b[:n,0]=bd[:,0]*dr;b[:n,1]=bd[:,1]
    a[n:n+m,n:n+m]=ac;a[n:n+m,:]+=np.outer(bm,measure);b[n:n+m,0]=br
    if not delay:
        b[:n,2]=bd[:,0]*dm;b[n:n+m,2]=bm
    else:
        for i in range(delay-1):a[n+m+i,n+m+i+1]=1
        a[-1,:n]=c;b[-1,2]=1
    cy=np.zeros((2,size));cy[0,:n]=c;cy[1]=ur
    direct=np.zeros((2,3));direct[1,0]=dr
    if not delay:direct[1,2]=dm
    return dict(compiler=COMPILER,controller=name,parameters=params,dt_s=dt,delay_samples=delay,
        plant=dict(A=ad.tolist(),B=bd.tolist(),C=c.tolist(),definition=p),
        controller_states=labels,closed=dict(A=a.tolist(),B=b.tolist(),C=cy.tolist(),D=direct.tolist()),
        input_order=["reference","disturbance","measurement_noise_before_delay"],output_order=["true_output","requested_input"],
        assumptions="zero-deviation LTI; no saturation; conditional integration inactive; no mode cancellation")

def response(model,omega):
    w=np.atleast_1d(omega);dt=model["dt_s"];p=model["plant"];a=np.array(p["A"]);b=np.array(p["B"]);c=np.array(p["C"])
    params=model["parameters"];q=np.exp(-1j*w*dt)
    alpha=math.exp(-dt/params["derivative_filter_s"]) if params["derivative_filter_s"] else 0.
    integral=params["ki"]*dt/(1-q);derivative=params["kd"]*(1-alpha)*(1-q)/(dt*(1-alpha*q))
    cy=params["kp"]+integral+derivative;cr=params["kp"]*params.get("beta",1.)+integral
    gu=np.full(len(w),complex(np.nan,np.nan));gd=gu.copy()
    for i,z in enumerate(1/q):
        matrix=z*np.eye(len(a))-a
        try:
            if np.linalg.cond(matrix)>1e13:continue
            values=c@np.linalg.solve(matrix,b);gu[i],gd[i]=values
        except np.linalg.LinAlgError:pass
    loop=gu*cy*q**model["delay_samples"]
    with np.errstate(divide="ignore",invalid="ignore",over="ignore"):
        sensitivity=1/(1+loop);complement=loop*sensitivity
        return dict(L=loop,S=sensitivity,T=complement,Y_R=gu*cr*sensitivity,Y_D=gd*sensitivity,
                    Y_N=-complement,U_N=-cy*q**model["delay_samples"]*sensitivity,
                    loop_without_delay=gu*cy)

def pole_summary(model):
    a=np.array(model["closed"]["A"]);values,vectors=np.linalg.eig(a)
    radius=float(max(abs(values),default=0))
    residual=float(np.linalg.norm(a@vectors-vectors*values)/max(1.,np.linalg.norm(a)))
    state="numerically_uncertain" if not math.isfinite(residual) or residual>1e-8 else "stable" if radius<1-1e-8 else "unstable" if radius>1+1e-8 else "boundary"
    return dict(state=state,spectral_radius=radius,tolerance=1e-8,eigen_residual=residual,
        poles=[dict(real=float(z.real),imag=float(z.imag),modulus=float(abs(z))) for z in values])
