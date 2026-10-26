"""Independent DOP853 replay of saved custom LTI trajectories; no product imports.

Builds the dual state model with SciPy tf2ss from polynomial definitions, rather
than using product matrices or its matrix-exponential transition. Replays actual
held input/disturbance; this checks simulation arithmetic, not hardware validity.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import warnings

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.signal import BadCoefficients,tf2ss


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def system(p):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore",BadCoefficients)
        a,_,cu,_=tf2ss(p["numerator"],p["denominator"])
        _,_,cd,_=tf2ss(p["disturbance_numerator"] or [0.],p["denominator"])
    return a.T/p["time_scale"],np.column_stack((cu[0]*p["gain_scale"],cd[0]))/p["time_scale"]


def replay(folder,definition,trace,snapshot_name,preview=False):
    a,b=system(definition);x=np.asarray(definition["initial_state"],dtype=float)
    frozen=read(folder/snapshot_name)
    np.testing.assert_allclose(frozen["continuous"]["A"],a,atol=1e-12,rtol=1e-12)
    np.testing.assert_allclose(frozen["continuous"]["B"],b,atol=1e-12,rtol=1e-12)
    with (folder/trace).open(encoding="utf-8") as stream:rows=list(csv.DictReader(stream))
    error=abs(x[0]-float(rows[0]["output"]));largest=abs(x[0])
    for row,following in zip(rows,rows[1:]):
        dt=float(following["time_s"])-float(row["time_s"])
        inputs=np.array([float(row["input" if preview else "applied_input"]),float(row["disturbance"])])
        solution=solve_ivp(lambda t,z:a@z+b@inputs,(0,dt),x,method="DOP853",rtol=2e-11,atol=2e-13)
        if not solution.success:raise ValueError(solution.message)
        x=solution.y[:,-1];expected=float(following["output"])
        error=max(error,abs(x[0]-expected));largest=max(largest,abs(expected))
    tolerance=2e-8*(1+largest)
    return dict(trace=trace,samples=len(rows),max_abs_error=float(error),tolerance=float(tolerance),passed=bool(error<=tolerance))


def audit(folder):
    folder=Path(folder).resolve()
    checks=read(folder/"checksums.json")
    for name,wanted in checks.items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder):raise ValueError("checksum path escapes suite")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=wanted:raise ValueError("checksum mismatch: "+name)
    manifest=read(folder/"manifest.json")
    if read(folder/"status.json")["state"]!="completed":raise ValueError("audit requires completed numerical examples")
    results=[]
    if manifest["schema_version"]=="model-preview-1.0":
        results.append(replay(folder,manifest["config"]["plant"],"preview.csv","model-snapshot.json",True))
    else:
        for file in sorted((folder/"runs").glob("*.json")):
            record=read(file)
            if record.get("model_name")!="transfer_function":continue
            if record["metrics"]["status"]!="completed":raise ValueError("cannot assert numerical agreement for failed run")
            p=record["plant"]
            model_path=record.get("model_snapshot","model-snapshot.json")
            results.append(replay(folder,p,record["trace_file"],model_path))
    if not results:raise ValueError("no custom LTI traces found")
    return dict(folder=str(folder),trajectories=results,passed=all(x["passed"] for x in results))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite",type=Path,action="append",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=dict(scope="synthetic LTI numerical replay, not hardware or robust stability validation",
        reference="independent dual tf2ss + DOP853; no product imports",python=platform.python_version(),
        numpy=np.__version__,scipy=scipy.__version__,suites=[audit(folder) for folder in args.suite])
    report["passed"]=all(s["passed"] for s in report["suites"])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print("Independent LTI replay:",report["passed"],"traces:",sum(len(s["trajectories"]) for s in report["suites"]))
    if not report["passed"]:raise SystemExit(1)

if __name__=="__main__":main()

