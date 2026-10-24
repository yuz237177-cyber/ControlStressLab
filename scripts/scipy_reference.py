"""Standalone SciPy oracle. Never imports the product or reads its trajectories.

Compatible with Python 3.9 so an existing scientific environment can be used.
Only the JSON input suite is accepted; integration and controller state are local.
"""

import argparse
import json
import math
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.signal import cont2discrete, dlsim


def coefficients(case):
    p = case["plant"]
    if case["model"] == "FirstOrder":
        return -1 / p["tau_s"], p["gain"] / p["tau_s"], 1 / p["tau_s"]
    # Construct the continuous ODE, not the product's equilibrium/expm1 update.
    j, b, r, kt, ke = (p[n] for n in (
        "inertia_kg_m2", "friction_Nm_s", "resistance_ohm", "torque_Nm_A", "back_emf_V_s"))
    return -(b + kt * ke / r) / j, kt / (r * j), -1 / j


def signals(case):
    n, dt = case["intervals"], case["dt_s"]
    result = []
    for name in ("reference", "load"):
        values = np.zeros(n + 1)
        for event, value in case[name]:
            values[int(round(event / dt)):] = value
        result.append(values)
    return result


def discretize(case):
    a, g, h = coefficients(case)
    system = tuple(np.asarray(m, dtype=float) for m in ([[a]], [[g, h]], [[1.0]], [[0.0, 0.0]]))
    return cont2discrete(system, case["dt_s"], method="zoh")


def calculate(case):
    n, dt = case["intervals"], case["dt_s"]
    initial = case["plant"]["initial_output"]
    reference, load = signals(case)
    times = np.arange(n + 1) * dt
    if case["path"] == "open_loop":
        commands = np.array(case["input"])
        # No explicit t: exactly one discrete step per input, no interpolation.
        _, y, _ = dlsim(discretize(case), np.column_stack((commands, load)), x0=[initial])
        return {"time": times.tolist(), "output": y[:, 0].tolist(), "command": commands[:-1].tolist() + [None]}
    p = case["controller"]
    if case["path"] == "linear_pi":
        ad, bd, _, _, _ = discretize(case)
        a, g, h = ad[0, 0], bd[0, 0], bd[0, 1]
        q = p["kp"] + p["ki"] * dt
        augmented = (np.array([[a - g*q, g], [-p["ki"]*dt, 1.0]]),
                     np.array([[g*q, h], [p["ki"]*dt, 0.0]]),
                     np.array([[1.0, 0.0]]), np.zeros((1, 2)), dt)
        _, y, states = dlsim(augmented, np.column_stack((reference, load)), x0=[initial, 0.0])
        u = -q * y[:, 0] + states[:, 1] + q * reference
        if np.any(np.abs(u[:-1]) >= case["voltage_limit"]):
            raise ValueError("linear PI reference unexpectedly reaches saturation")
        return {"time": times.tolist(), "output": y[:, 0].tolist(), "measurement": y[:, 0].tolist(),
                "command": u[:-1].tolist() + [None], "applied": u[:-1].tolist() + [None]}
    a, g, h = coefficients(case)
    y, integral, derivative, previous = initial, 0.0, 0.0, None
    raw, outputs, measured, commands, applied = [], [], [], [], []
    delay = int(round(case["delay_s"] / dt))
    alpha = math.exp(-dt / p["derivative_filter_s"]) if p["derivative_filter_s"] else 0.0
    for k in range(n + 1):
        outputs.append(float(y))
        raw.append(y + case["noise"][k])
        m = initial if k < delay else raw[k - delay]
        measured.append(float(m))
        if k == n:
            commands.append(None)
            applied.append(None)
            break
        error = reference[k] - m
        slope = 0.0 if previous is None else (m - previous) / dt
        derivative = alpha * derivative + (1 - alpha) * slope
        previous = m
        candidate = integral + p["ki"] * error * dt
        requested = p["kp"] * error + candidate - p["kd"] * derivative
        actual = np.clip(requested, -case["voltage_limit"], case["voltage_limit"])
        if not p["anti_windup"] or error * (requested - actual) <= 0:
            integral = candidate
        commands.append(float(requested))
        applied.append(float(actual))
        solution = solve_ivp(lambda t, x: a*x + g*actual + h*load[k], (0.0, dt), [y],
                             method="DOP853", rtol=1e-11, atol=1e-12)
        if not solution.success:
            raise RuntimeError(solution.message)
        y = float(solution.y[0, -1])
    return {"time": times.tolist(), "output": outputs, "measurement": measured,
            "command": commands, "applied": applied}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suite = json.loads(args.input.read_text(encoding="utf8"))
    cases = {}
    for c in suite["cases"]:
        cases[c["id"]] = calculate(c)
    result = {"environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
              "methods": {"linear": "cont2discrete(zoh) + dlsim", "nonlinear": "solve_ivp(DOP853)",
                          "rtol": 1e-11, "atol": 1e-12}, "cases": cases}
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
