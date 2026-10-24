"""Independent SciPy state-space replay of plants and linear ADRC requests.

No product imports. Plant replay checks held dynamics, not closed-loop performance.
ADRC replay treats recorded measurements/previous applied inputs as exogenous inputs
and verifies the independent augmented discrete observer/controller matrices.
Compatible with a separate Python 3.9 scientific environment.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.signal import cont2discrete, dlsim


def plant_system(record):
    p, name = record["plant"], record["model_name"]
    if name == "first_order":
        a = [[-1/p["tau_s"]]]
        b = [[p["gain"]/p["tau_s"], 1/p["tau_s"]]]
        initial = [p["initial_output"]]
    elif name == "reduced_motor":
        j, r, kt, ke = (p[k] for k in ("inertia_kg_m2", "resistance_ohm", "torque_Nm_A", "back_emf_V_s"))
        a, b = [[-(p["friction_Nm_s"]+kt*ke/r)/j]], [[kt/(r*j), -1/j]]
        initial = [p["initial_output"]]
    elif name == "inductive_motor":
        j, l = p["inertia_kg_m2"], p["inductance_H"]
        a = [[-p["friction_Nm_s"]/j, p["torque_Nm_A"]/j], [-p["back_emf_V_s"]/l, -p["resistance_ohm"]/l]]
        b = [[0, -1/j], [1/l, 0]]
        initial = [p["initial_output"], p["initial_current_A"]]
    elif name in ("mass_spring_damper", "second_order"):
        m = p["mass_kg"]
        a = [[0, 1], [-p["stiffness_N_m"]/m, -p["damping_N_s_m"]/m]]
        b = [[0, 0], [1/m, 1/m]]
        initial = [p["initial_output"], p["initial_velocity_m_s"]]
    else:
        raise ValueError("unrecognized physical model")
    c = [[1.0]+[0.0]*(len(a)-1)]
    system = tuple(np.asarray(x, dtype=float) for x in (a, b, c, [[0, 0]]))
    return cont2discrete(system, record["scenario"]["dt_s"], method="zoh"), initial


def adrc_system(record):
    p, dt = record["controller"], record["scenario"]["dt_s"]
    wo, wc, b0 = p["observer_bandwidth"], p["control_bandwidth"], p["b0"]
    if p["relative_degree"] == 1:
        a = np.array([[0., 1.], [0., 0.]])
        l, b, h, kr = [2*wo, wo**2], [b0, 0.], [-wc/b0, -1/b0], wc/b0
    else:
        a = np.array([[0., 1., 0.], [0., 0., 1.], [0., 0., 0.]])
        l, b, h, kr = [3*wo, 3*wo**2, wo**3], [0., b0, 0.], [-wc**2/b0, -2*wc/b0, -1/b0], wc**2/b0
    l, b, h = np.array(l), np.array(b), np.array([h])
    c = np.zeros((1, len(a)))
    c[0, 0] = 1
    f = np.eye(len(a))+dt*(a-l[:, None]@c)
    g = np.column_stack((dt*l, dt*b, np.zeros(len(a))))
    direct = h@g
    direct[0, 2] = kr
    # Output uses the updated observer state, therefore C=H*F and D=H*G+K_r.
    return (f, g, h@f, direct, dt)


def check(a, b):
    a, b = np.asarray(a), np.asarray(b)
    error = np.abs(a-b)
    allowed = 1e-8+1e-9*np.abs(b)
    return dict(passed=bool(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all() and np.all(error <= allowed)),
                max_abs_error=float(np.max(error)), max_tolerance_fraction=float(np.max(error/allowed)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    status = json.loads((args.suite / "status.json").read_text(encoding="utf8"))
    if not status["artifacts_complete"]: raise ValueError("incomplete suite")
    checksums = json.loads((args.suite / "checksums.json").read_text(encoding="utf8"))
    for name, value in checksums.items():
        if hashlib.sha256((args.suite / name).read_bytes()).hexdigest() != value: raise ValueError("checksum mismatch: "+name)
    results = []
    for file in sorted((args.suite / "runs").glob("*.json")):
        record = json.loads(file.read_text(encoding="utf8"))
        with (args.suite / record["trace_file"]).open(encoding="utf8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if record["metrics"]["status"] != "completed":
            results.append(dict(case_id=record["case_id"], passed=False, reason="incomplete_product_run"))
            continue
        inputs = np.array([[float(r["applied_input"]) if r["applied_input"] else 0., float(r["disturbance"])] for r in rows])
        system, initial = plant_system(record)
        _, y, _ = dlsim(system, inputs, x0=initial)
        plant = check([float(r["output"]) for r in rows], y[:, 0])
        observer = None
        if record["controller_name"] == "LADRC":
            measurement = [float(r["measurement"]) for r in rows[:-1]]
            previous_input = [0.]+inputs[:-2, 0].tolist()
            refs = [float(r["reference"]) for r in rows[:-1]]
            system = adrc_system(record)
            initial = np.zeros(system[0].shape[0])
            initial[0] = measurement[0]
            _, u, _ = dlsim(system, np.column_stack((measurement, previous_input, refs)), x0=initial)
            observer = check([float(r["requested_input"]) for r in rows[:-1]], u[:, 0])
        results.append(dict(case_id=record["case_id"], plant=plant, adrc_requests=observer,
                            passed=plant["passed"] and (observer is None or observer["passed"])))
    manifest = json.loads((args.suite / "manifest.json").read_text(encoding="utf8"))
    expected = manifest["raw_trace_runs"] if manifest.get("schema_version") == "benchmark-1.0" else status["expected_runs"]
    if len(results) != expected: raise ValueError("record count mismatch")
    result = dict(environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__),
                  suite=str(args.suite), expected_runs=expected, plant_replays=len(results),
                  adrc_request_replays=sum(r.get("adrc_requests") is not None for r in results),
                  failed=sum(not r["passed"] for r in results), cases=results,
                  scope="plant input replay + independent linear ADRC matrices; not a new full independent nonlinear closed-loop simulation",
                  reference_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(f"Plant replays={len(results)}, ADRC request replays={result['adrc_request_replays']}, failures={result['failed']}")
    if result["failed"]: raise SystemExit(1)


if __name__ == "__main__": main()
