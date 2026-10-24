"""Deterministic sample/hold loop. No controller receives hidden plant state."""

from dataclasses import dataclass, field, fields, is_dataclass
import json
import math
from numbers import Real
import random
import traceback
from typing import Protocol

from .models import positive

MAX_SAMPLE_COUNT = 200_000


class Plant(Protocol):
    output: float

    def reset(self) -> None: ...
    def advance(self, u: float, disturbance: float, dt: float) -> None: ...


class Controller(Protocol):
    def reset(self) -> None: ...
    def command(self, reference: float, measurement: float, dt: float) -> float: ...
    def observe_applied(self, applied: float) -> None: ...


@dataclass(frozen=True)
class StepSignal:
    """Right-continuous steps (time_s, value). Changes must align with sample grid."""

    points: tuple[tuple[float, float], ...] = ((0.0, 0.0),)

    def __post_init__(self) -> None:
        if not self.points or self.points[0][0] != 0:
            raise ValueError("signals must start at t=0")
        if any(not math.isfinite(x) for pair in self.points for x in pair):
            raise ValueError("signal points must be finite")
        if any(a[0] >= b[0] for a, b in zip(self.points, self.points[1:])):
            raise ValueError("signal times must be strictly increasing")

    def at(self, t: float) -> float:
        value = self.points[0][1]
        for time_s, new_value in self.points[1:]:
            if time_s > t + 1e-12:
                break
            value = new_value
        return value


@dataclass(frozen=True)
class Scenario:
    name: str = "nominal"
    dt_s: float = 0.01
    duration_s: float = 12.0
    reference: StepSignal = field(default_factory=lambda: StepSignal(((0.0, 0.0), (0.5, 60.0))))
    load: StepSignal = field(default_factory=StepSignal)
    noise_std: float = 0.0
    measurement_delay_s: float = 0.0
    voltage_limit: float = 12.0
    output_bound: float = 1000.0
    seed: int = 42
    evaluation_start_s: float = 0.5
    recovery_start_s: float = 0.5
    recovery_band: float = 1.2
    recovery_dwell_s: float = 0.5
    evidence: str = "synthetic_assumption"

    def __post_init__(self) -> None:
        for name in ("dt_s", "duration_s", "voltage_limit", "output_bound", "recovery_band", "recovery_dwell_s"):
            positive(getattr(self, name), name)
        for name in ("noise_std", "measurement_delay_s", "evaluation_start_s", "recovery_start_s"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        count = self.duration_s / self.dt_s
        if not math.isfinite(count) or count > MAX_SAMPLE_COUNT:
            raise ValueError(f"sample count exceeds the {MAX_SAMPLE_COUNT} interval limit")
        times = [self.duration_s, self.measurement_delay_s, self.evaluation_start_s,
                 self.recovery_start_s, self.recovery_dwell_s]
        times.extend(t for signal in (self.reference, self.load) for t, _ in signal.points)
        if any(not math.isclose(t / self.dt_s, round(t / self.dt_s), abs_tol=1e-8, rel_tol=0) for t in times):
            raise ValueError("duration, delay, evaluation windows and signal changes must align with dt_s")
        if self.measurement_delay_s > self.duration_s:
            raise ValueError("measurement delay exceeds duration")
        if not 0 <= self.evaluation_start_s < self.duration_s:
            raise ValueError("evaluation_start_s must be inside the run")
        if not 0 <= self.recovery_start_s < self.duration_s:
            raise ValueError("recovery_start_s must be inside the run")
        if self.recovery_start_s + self.recovery_dwell_s > self.duration_s:
            raise ValueError("recovery dwell does not fit the observation window")
        if any(t >= self.duration_s for s in (self.reference, self.load) for t, _ in s.points[1:]):
            raise ValueError("signal change must precede the end of the run")
        if any(t > self.recovery_start_s for t, _ in self.reference.points):
            raise ValueError("recovery metric requires a constant reference after recovery_start_s")
        if self.evidence != "synthetic_assumption":
            raise ValueError("v0.1 scenarios are synthetic; measured validation is not implemented")

    def noise_sequence(self) -> tuple[float, ...]:
        # Pre-generate outside controller execution, paired across controller comparisons.
        rng = random.Random(self.seed)
        return tuple(rng.gauss(0.0, self.noise_std) for _ in range(round(self.duration_s / self.dt_s) + 1))


@dataclass
class Run:
    scenario: Scenario
    rows: list[dict]
    status: str
    reason: str
    plant: dict
    controller: dict
    termination_time_s: float
    last_integrated_time_s: float = 0.0
    failure: dict | None = None
    diagnostics: list[str] = field(default_factory=list)


def parameters(obj: object) -> dict:
    """Capture initial public configuration, never dynamic controller state."""
    if callable(getattr(obj, "to_config", None)):
        config = obj.to_config()
        if not isinstance(config, dict):
            raise TypeError("to_config() must return a dictionary")
    elif is_dataclass(obj):
        config = {f.name: getattr(obj, f.name) for f in fields(obj)
                  if f.init and not f.name.startswith("_") and f.name != "output"}
    else:
        return {"type": type(obj).__name__, "params_recorded": False}
    # Validate and detach configuration before any reset/command modifies the object.
    config = json.loads(json.dumps(config, allow_nan=False))
    return {**config, "type": type(obj).__name__, "params_recorded": True}


def scalar(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real scalar")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def simulate(plant: Plant, controller: Controller, scenario: Scenario, *, fail_fast: bool = False) -> Run:
    """Record failures by default; fail_fast re-raises for debugging. Interrupts propagate."""
    rows: list[dict] = []
    run = Run(scenario, rows, "completed", "", {"type": type(plant).__name__},
              {"type": type(controller).__name__}, 0.0)
    if scenario.measurement_delay_s == scenario.duration_s:
        run.diagnostics.append("no_live_measurement_during_control")
    phase = "metadata"
    t = 0.0
    try:
        run.plant, run.controller = parameters(plant), parameters(controller)
        for name, info in (("plant", run.plant), ("controller", run.controller)):
            if not info.get("params_recorded"):
                run.diagnostics.append(f"{name}_parameters_not_recorded")
        phase = "plant.reset"
        plant.reset()
        phase = "controller.reset"
        controller.reset()
        noise = scenario.noise_sequence()
        delay = round(scenario.measurement_delay_s / scenario.dt_s)
        samples = round(scenario.duration_s / scenario.dt_s)
        measurements: list[float] = []
        initial = None
        for k in range(samples + 1):
            t = k * scenario.dt_s
            run.termination_time_s = t
            row = {"time_s": t, "reference_rad_s": scenario.reference.at(t),
                   "true_output_rad_s": None, "measurement_rad_s": None,
                   "command_V": None, "applied_V": None, "load_Nm": scenario.load.at(t),
                   "interval_s": 0.0, "action_taken": False, "transition_completed": False}
            rows.append(row)
            phase = "plant.output"
            y = scalar(plant.output, "plant output")
            row["true_output_rad_s"] = y
            if initial is None:
                initial = y
            phase = "measurement"
            sample = scalar(y + noise[k], "measurement sample")
            measurements.append(sample)
            measured = measurements[k - delay] if k >= delay else initial
            row["measurement_rad_s"] = scalar(measured, "available measurement")
            if abs(y) > scenario.output_bound:
                run.status, run.reason = "bound_exceeded", "output exceeded observation bound"
                break
            if k == samples:
                break
            phase = "controller.command"
            requested = scalar(controller.command(row["reference_rad_s"], measured, scenario.dt_s), "controller output")
            row["command_V"] = requested
            applied = max(-scenario.voltage_limit, min(scenario.voltage_limit, requested))
            phase = "controller.observe_applied"
            controller.observe_applied(applied)
            row["applied_V"] = applied
            row["action_taken"] = True
            phase = "plant.advance"
            plant.advance(applied, row["load_Nm"], scenario.dt_s)
            # A transition is recorded as complete only after advance succeeds.
            row["interval_s"] = scenario.dt_s
            row["transition_completed"] = True
            run.last_integrated_time_s = (k + 1) * scenario.dt_s
    except Exception as exc:
        if fail_fast:
            raise
        numeric_phase = phase not in ("metadata", "plant.reset", "controller.reset")
        run.status = "numerical_failure" if isinstance(exc, (ArithmeticError, ValueError)) and numeric_phase else "interface_error"
        run.reason = f"{phase}: {type(exc).__name__}: {exc}"
        run.termination_time_s = t
        run.failure = {"phase": phase, "type": type(exc).__name__, "message": str(exc),
                       "traceback": traceback.format_exc()}
    return run
