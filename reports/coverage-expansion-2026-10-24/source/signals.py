"""Finite sampled waveforms, explicitly held constant over each control interval."""

from dataclasses import dataclass, field
import math
import random


@dataclass(frozen=True)
class SampledSignal:
    dt_s: float
    values: tuple[float, ...]
    recipe: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "values", tuple(self.values))
        if not math.isfinite(self.dt_s) or self.dt_s <= 0:
            raise ValueError("signal dt_s must be finite and positive")
        if not 2 <= len(self.values) <= 200_001 or any(not math.isfinite(v) for v in self.values):
            raise ValueError("signal needs 2..200001 finite samples")

    def at(self, t: float) -> float:
        if not math.isfinite(t) or t < -1e-12 or t > (len(self.values)-1)*self.dt_s + 1e-12:
            raise ValueError("time outside sampled signal")
        k = min(len(self.values)-1, math.floor(t/self.dt_s + 1e-10))
        return self.values[max(0, k)]

    def validate_grid(self, dt: float, duration: float):
        if not math.isclose(self.dt_s, dt, abs_tol=1e-14, rel_tol=0) or len(self.values) != round(duration/dt) + 1:
            raise ValueError("sampled signal grid differs from scenario")

    def constant_after(self, start: float) -> bool:
        tail = self.values[round(start/self.dt_s):]
        return bool(tail) and all(v == tail[0] for v in tail)


def waveform(kind: str, *, dt_s=0.01, duration_s=16.0, amplitude=1.0, offset=0.0,
             start_s=0.5, frequency_hz=0.25, stop_frequency_hz=0.8,
             ramp_duration_s=4.0, pulse_width_s=1.0, hold_s=0.5, seed=42) -> SampledSignal:
    kinds = ("constant", "step", "ramp", "sine", "triangle", "chirp", "multistep", "pulse", "square", "prbs")
    if kind not in kinds:
        raise ValueError("unknown waveform kind")
    numbers = (dt_s, duration_s, amplitude, offset, start_s, frequency_hz, stop_frequency_hz,
               ramp_duration_s, pulse_width_s, hold_s)
    if not all(math.isfinite(v) for v in numbers) or min(dt_s, duration_s, ramp_duration_s, pulse_width_s, hold_s) <= 0:
        raise ValueError("waveform parameters must be finite with positive durations")
    if not 0 <= start_s < duration_s or not 1 <= duration_s/dt_s <= 200_000:
        raise ValueError("waveform interval or resource limit")
    for t in (duration_s, start_s, ramp_duration_s, pulse_width_s, hold_s):
        if not math.isclose(t/dt_s, round(t/dt_s), abs_tol=1e-8, rel_tol=0):
            raise ValueError("waveform events and blocks must align with dt_s")
    if kind in ("sine", "triangle", "square", "chirp"):
        maximum = max(frequency_hz, stop_frequency_hz) if kind == "chirp" else frequency_hz
        if frequency_hz <= 0 or (kind == "chirp" and stop_frequency_hz <= 0) or maximum*dt_s > 0.1:
            raise ValueError("periodic signals need at least ten samples per highest fundamental period")
    if kind == "ramp" and start_s + ramp_duration_s >= duration_s:
        raise ValueError("ramp must finish before terminal sample")
    if kind == "pulse" and start_s + pulse_width_s >= duration_s:
        raise ValueError("pulse must finish before terminal sample")
    if kind == "multistep" and start_s + 6 >= duration_s:
        raise ValueError("multistep needs six seconds after start")
    rng, blocks = random.Random(seed), {}
    values = []
    start = round(start_s/dt_s)
    for k in range(round(duration_s/dt_s)+1):
        elapsed = (k-start)*dt_s
        shape = 0.0
        if k >= start:
            phase = 2*math.pi*frequency_hz*elapsed
            if kind == "step": shape = 1.0
            elif kind == "constant": shape = 0.0
            elif kind == "ramp": shape = min((k-start)/round(ramp_duration_s/dt_s), 1.0)
            elif kind == "sine": shape = math.sin(phase)
            elif kind == "triangle": shape = 2/math.pi*math.asin(math.sin(phase))
            elif kind == "square": shape = 1.0 if ((k-start)*dt_s*frequency_hz) % 1 < 0.5 else -1.0
            elif kind == "chirp":
                rate = (stop_frequency_hz-frequency_hz)/(duration_s-start_s)
                shape = math.sin(2*math.pi*(frequency_hz*elapsed + 0.5*rate*elapsed**2))
            elif kind == "pulse": shape = float(k-start < round(pulse_width_s/dt_s))
            elif kind == "multistep": shape = 1.0 if elapsed < 3-1e-12 else (-0.5 if elapsed < 6-1e-12 else 0.7)
            elif kind == "prbs":
                block = (k-start)//round(hold_s/dt_s)
                if block not in blocks: blocks[block] = rng.choice((-1.0, 1.0))
                shape = blocks[block]
        values.append(offset + amplitude*shape)
    recipe = {"kind": kind, "amplitude": amplitude, "offset": offset, "start_s": start_s,
              "frequency_hz": frequency_hz, "stop_frequency_hz": stop_frequency_hz,
              "ramp_duration_s": ramp_duration_s, "pulse_width_s": pulse_width_s, "hold_s": hold_s,
              "seed": seed, "hold": "zero_order", "prbs_construction": "random_binary_blocks" if kind == "prbs" else None}
    return SampledSignal(dt_s, tuple(values), recipe)
