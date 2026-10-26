"""Independent frequency and internal-pole audit; never imports product code."""
import argparse,csv,json,math
from pathlib import Path
import numpy as np
from scipy.signal import cont2discrete,tf2ss
from scipy.optimize import linear_sum_assignment
import control

def plant(base):
    p=base["plant"];dt=base["conditions"]["dt_s"]
    if base["model"]=="first_order":
        a=[[-1/p["tau_s"]]];b=[[p["gain"]/p["tau_s"],1/p["tau_s"]]];c=[[1.]]
    elif base["model"]=="second_order":
        a=[[0,1],[-p["stiffness_N_m"]/p["mass_kg"],-p["damping_N_s_m"]/p["mass_kg"]]]
        b=[[0,0],[1/p["mass_kg"],1/p["mass_kg"]]];c=[[1.,0.]]
    else:
        a0,_,cu,_=tf2ss(p["numerator"],p["denominator"]);_,_,cd,_=tf2ss(p["disturbance_numerator"] or [0.],p["denominator"])
        a=a0.T/p["time_scale"];b=np.column_stack((cu[0]*p["gain_scale"],cd[0]))/p["time_scale"];c=[[1.]+[0.]*(len(a)-1)]
    ad,bd,cd,dd,_=cont2discrete((np.array(a),np.array(b),np.array(c),np.zeros((1,2))),dt,method="zoh")
    return ad,bd,cd[0]

def internal(ad,bd,c,params,dt,delay):
    n=len(ad);use_i=params["ki"]!=0;use_d=params["kd"]!=0;alpha=math.exp(-dt/params["derivative_filter_s"]) if params["derivative_filter_s"] else 0
    size=n+int(use_i)+int(use_d)+int(use_d and alpha!=0)+delay
    def step(state):
        i=n;integral=state[i] if use_i else 0.;i+=int(use_i)
        previous=state[i] if use_d else 0.;i+=int(use_d)
        derivative=state[i] if use_d and alpha else 0.;i+=int(use_d and alpha!=0)
        output=float(c@state[:n]);measurement=state[i] if delay else output
        integral-=params["ki"]*dt*measurement
        derivative=alpha*derivative+(1-alpha)*(measurement-previous)/dt if use_d else 0
        command=-params["kp"]*measurement+integral-params["kd"]*derivative
        following=list(ad@state[:n]+bd[:,0]*command)
        if use_i:following.append(integral)
        if use_d:following.append(measurement)
        if use_d and alpha:following.append(derivative)
        if delay:following+=list(state[i+1:])+[output]
        return following
    return np.column_stack([step(row) for row in np.eye(size)])

def audit(folder):
    folder=Path(folder);config=json.loads((folder/"config.json").read_text(encoding="utf-8"))
    base=config["base"];dt=base["conditions"]["dt_s"];delay=round(base["conditions"]["measurement_delay_s"]/dt)
    ad,bd,c=plant(base)
    gu=control.ss(ad,bd[:,[0]],c.reshape(1,-1),[[0.]],dt)
    gd=control.ss(ad,bd[:,[1]],c.reshape(1,-1),[[0.]],dt)
    results=[]
    for name in base["selected_controllers"]:
        params=next(v["parameters"] for v in base["controllers"] if v["name"]==name)
        with (folder/"frequency"/(name+".csv")).open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
        w=np.array([float(v["omega_rad_s"]) for v in rows]);z=np.exp(1j*w*dt);q=1/z
        pu=np.array([complex(control.evalfr(gu,v)) for v in z]);pd=np.array([complex(control.evalfr(gd,v)) for v in z])
        alpha=math.exp(-dt/params["derivative_filter_s"]) if params["derivative_filter_s"] else 0
        integ=params["ki"]*dt/(1-q);deriv=params["kd"]*(1-alpha)*(1-q)/dt/(1-alpha*q)
        cy=params["kp"]+integ+deriv;cr=params["kp"]*params.get("beta",1.)+integ
        loop=pu*cy*q**delay;s=1/(1+loop)
        expected=dict(L=loop,S=s,T=loop*s,Y_R=pu*cr*s,Y_D=pd*s,Y_N=-loop*s,U_N=-cy*q**delay*s)
        worst=0.;compared=0
        for i,row in enumerate(rows):
            for key,value in expected.items():
                if row[key+"_real"] and np.isfinite(value[i]):
                    actual=complex(float(row[key+"_real"]),float(row[key+"_imag"]))
                    error=abs(actual-value[i])/(1+abs(value[i]));worst=max(worst,error);compared+=1
        product=json.loads((folder/"models"/(name+".json")).read_text(encoding="utf-8"))
        eigen=np.linalg.eigvals(internal(ad,bd,c,params,dt,delay));wanted=np.linalg.eigvals(product["closed"]["A"])
        cost=abs(eigen[:,None]-wanted[None,:]);a,b=linear_sum_assignment(cost);pole_error=float(max(cost[a,b],default=0))
        gm,pm,_,wpc,wgc,_=control.stability_margins((abs(loop),np.unwrap(np.angle(loop))*180/np.pi,w),returnall=True)
        summary=next(v for v in json.loads((folder/"summary.json").read_text(encoding="utf-8")) if v["controller"]==name)
        margins=[]
        for reference,kind in ((wpc,"phase"),(wgc,"gain")):
            actual=[r for r in summary["crossovers"] if r["kind"]==kind]
            for v in reference:
                nearest=min((abs(r["omega_rad_s"]/v-1) for r in actual),default=float("inf"))
                margins.append(float(nearest))
        passed=worst<1e-8 and pole_error<1e-5 and all(v<1e-3 for v in margins)
        results.append(dict(controller=name,frequency_values_compared=compared,max_relative_complex_error=float(worst),
            max_internal_pole_error=pole_error,reference_crossovers=len(margins),max_crossover_relative_difference=max(margins,default=None),passed=bool(passed)))
    return dict(folder=str(folder),controllers=results,passed=all(r["passed"] for r in results))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--suite",type=Path,action="append",required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();results=[audit(p) for p in args.suite]
    report=dict(reference="SciPy ZOH + independent PID state stepping + python-control FRD; no product imports",control_version=control.__version__,suites=results,passed=all(r["passed"] for r in results))
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print("Independent frequency reference:",report["passed"])
    if not report["passed"]:raise SystemExit(1)
if __name__=="__main__":main()

