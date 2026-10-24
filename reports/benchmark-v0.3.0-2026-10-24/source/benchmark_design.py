"""Predeclared budgeted search and held-out scenarios; no optimizer dependencies."""

from copy import deepcopy
import hashlib
import math

from .controllers import PID
from .coverage import controllers, model_spec
from .extended_controllers import LinearADRC, TwoDOFPID
from .extended_models import MassSpringDamper
from .models import FirstOrder
from .signals import waveform
from .simulation import Scenario, parameters

MODELS = ("first_order", "second_order")
CONTROLLERS = ("PI", "PID_aw", "TwoDOF_PID", "LADRC")
FAMILIES = ("sine", "chirp", "binary_disturbance", "noise_delay")
TRAINING = ("step", "ramp", "disturbance_step")
DEFAULT_CONFIG = dict(protocol="budgeted-siso-1.0", models=list(MODELS), controllers=list(CONTROLLERS),
    candidate_budget=32, search_seed=9173, heldout_seeds=[101, 202, 303], parameter_factors=[0.65, 1.0, 1.5],
    max_training_variation_rate=0.6, max_training_saturation_fraction=0.25)


def validate_config(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT_CONFIG):
        raise ValueError("config must contain exactly the documented benchmark keys")
    config = deepcopy(value)
    if config["protocol"] != DEFAULT_CONFIG["protocol"]:
        raise ValueError("unsupported benchmark protocol")
    for key, allowed in (("models", MODELS), ("controllers", CONTROLLERS)):
        names = config[key]
        if not isinstance(names, list) or not names or any(not isinstance(n, str) or n not in allowed for n in names) or len(set(names)) != len(names):
            raise ValueError("invalid or repeated "+key)
    for key, low, high in (("candidate_budget", 1, 128), ("search_seed", 0, 2**32-1)):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError("invalid "+key)
    seeds = config["heldout_seeds"]
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 5 or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("heldout_seeds need 1..5 distinct unsigned integers")
    factors = config["parameter_factors"]
    if not isinstance(factors, list) or not 1 <= len(factors) <= 5 or any(type(f) not in (float, int) or not math.isfinite(f) or not 0.25 <= f <= 3 for f in factors) or len(set(factors)) != len(factors):
        raise ValueError("parameter_factors need 1..5 distinct finite factors in [0.25,3]")
    for key, low, high in (("max_training_variation_rate", 0, 100), ("max_training_saturation_fraction", 0, 1)):
        v = config[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError("invalid "+key)
    return config


def spec_for(model):
    if model not in MODELS:
        raise ValueError("unknown benchmark model")
    return model_spec("mass_spring_damper" if model == "second_order" else model)


def plant_for(model, factor=1.0):
    spec_for(model)
    return FirstOrder(tau_s=factor) if model == "first_order" else MassSpringDamper(mass_kg=factor)


def controller_for(name, params):
    cls = {"PI": PID, "PID_aw": PID, "TwoDOF_PID": TwoDOFPID, "LADRC": LinearADRC}[name]
    return cls(**params)


def candidate_parameters(model, name, config):
    if name not in CONTROLLERS:
        raise ValueError("unknown benchmark controller")
    baseline = dict(controllers(spec_for(model)))[name]
    base = {k: v for k, v in parameters(baseline).items() if k not in ("type", "params_recorded")}
    result = [base]
    ranges = dict(kp=(0.3, 6), ki=(0.1, 6), kd=(0.002, 0.6), wc=(0.5, 6)) if model == "first_order" else dict(kp=(1, 20), ki=(0.2, 8), kd=(0.2, 8), wc=(0.5, 4))
    for index in range(1, config["candidate_budget"]):
        def sample(key, bounds, linear=False):
            data = f"{config['search_seed']}|{model}|{index}|{key}".encode()
            # Top 53 bits produce an exactly representable unit-interval sample.
            u = (int.from_bytes(hashlib.sha256(data).digest()[:8], "big") >> 11)/2**53
            a, b = bounds
            return a+(b-a)*u if linear else math.exp(math.log(a)+(math.log(b)-math.log(a))*u)
        p = base.copy()
        if name == "LADRC":
            p["control_bandwidth"] = sample("wc", ranges["wc"])
            p["observer_bandwidth"] = min(20.0, p["control_bandwidth"]*sample("observer_ratio", (2, 5)))
        else:
            for key in ("kp", "ki") if name == "PI" else ("kp", "ki", "kd"):
                p[key] = sample(key, ranges[key])
            if name == "TwoDOF_PID":
                p["beta"] = sample("beta", (0.3, 1), linear=True)
        result.append(p)
    return result


def heldout_cases(config):
    return [dict(id=f"{family}__factor{factor:g}__seed{seed}", family=family, factor=factor, seed=seed)
            for family in FAMILIES for factor in config["parameter_factors"]
            for seed in (config["heldout_seeds"] if family in ("binary_disturbance", "noise_delay") else [0])]


def scenario_for(model, family, seed=0, *, heldout=False):
    spec = spec_for(model)
    scale = spec["scale"]
    def signal(kind, **kw):
        return waveform(kind, duration_s=12, **kw)
    ref = signal("step", amplitude=scale)
    load = signal("constant", amplitude=0)
    anchor, evaluation, mode = 0.5, 0.5, "settling"
    if not heldout:
        if family not in TRAINING: raise ValueError("unknown training scenario")
        if family == "ramp": ref, anchor = signal("ramp", amplitude=scale), 4.5
        if family == "disturbance_step":
            load = signal("step", amplitude=spec["disturbance"], start_s=6)
            anchor = evaluation = 6
    else:
        if family not in FAMILIES: raise ValueError("unknown heldout scenario")
        if family in ("sine", "chirp"):
            ref = signal(family, amplitude=0.35*scale, offset=0.65*scale,
                         frequency_hz=0.37 if family == "sine" else 0.11, stop_frequency_hz=0.61)
            mode = "tracking_only"
        if family == "binary_disturbance":
            load = signal("prbs", amplitude=spec["disturbance"], start_s=6, hold_s=0.4, seed=seed)
            anchor = evaluation = 6
            mode = "tracking_only"
    return Scenario(name=("heldout_" if heldout else "training_")+family, duration_s=12, reference=ref, load=load,
        voltage_limit=spec["limit"], output_bound=40*scale, seed=seed,
        noise_std=0.02*scale if heldout and family == "noise_delay" else 0,
        measurement_delay_s=0.07 if heldout and family == "noise_delay" else 0,
        evaluation_start_s=evaluation, recovery_start_s=anchor, recovery_mode=mode, recovery_band=0.02*scale)


def assess_candidate(metrics, config):
    """Accept training metrics only. Test data have no argument or scoring path."""
    keys = ("normalized_iae", "input_variation_rate", "saturation_fraction")
    valid = len(metrics) == len(TRAINING) and all(m["status"] == "completed" and
        all(type(m.get(k)) in (int, float) and math.isfinite(m[k]) for k in keys) for m in metrics)
    if not valid:
        return dict(feasible=False, objective=None, worst_variation_rate=None, worst_saturation_fraction=None)
    rate, sat = max(m["input_variation_rate"] for m in metrics), max(m["saturation_fraction"] for m in metrics)
    return dict(feasible=rate <= config["max_training_variation_rate"] and sat <= config["max_training_saturation_fraction"],
                objective=sum(m["normalized_iae"] for m in metrics)/len(metrics), worst_variation_rate=rate, worst_saturation_fraction=sat)


def select_candidate(candidates):
    feasible = [c for c in candidates if c["assessment"]["feasible"]]
    if not feasible: return None
    return min(feasible, key=lambda c: (c["assessment"]["objective"], c["candidate_index"]))
