"""Exact zero-order-hold transitions for illustrative continuous-time models."""

from dataclasses import dataclass
import math


def positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def finite_inputs(u: float, disturbance: float) -> None:
    if not math.isfinite(u) or not math.isfinite(disturbance):
        raise ValueError("input and disturbance must be finite")


@dataclass
class FirstOrder:
    """tau * dy/dt = -y + gain*u + disturbance (output-equivalent units)."""

    gain: float = 1.0
    tau_s: float = 1.0
    initial_output: float = 0.0
    output: float = 0.0

    def __post_init__(self) -> None:
        positive(self.tau_s, "tau_s")
        if not all(math.isfinite(x) for x in (self.gain, self.initial_output)):
            raise ValueError("model parameters must be finite")
        self.reset()

    def reset(self) -> None:
        self.output = self.initial_output

    def advance(self, u: float, disturbance: float, dt: float) -> None:
        positive(dt, "dt")
        finite_inputs(u, disturbance)
        equilibrium = self.gain * u + disturbance
        if not math.isfinite(equilibrium):
            raise ValueError("first-order equilibrium is not finite")
        self.output += (equilibrium - self.output) * (-math.expm1(-dt / self.tau_s))


@dataclass
class DCMotor:
    """Reduced DC motor: inductance omitted; omega [rad/s], u [V], load [N m].

    J*domega/dt = Kt*u/R - (b + Kt*Ke/R)*omega - load.
    Parameters are illustrative assumptions, NOT identified hardware values.
    """

    inertia_kg_m2: float = 0.01
    friction_Nm_s: float = 0.001
    resistance_ohm: float = 1.0
    torque_Nm_A: float = 0.1
    back_emf_V_s: float = 0.1
    initial_output: float = 0.0
    output: float = 0.0

    def __post_init__(self) -> None:
        for name in ("inertia_kg_m2", "resistance_ohm", "torque_Nm_A", "back_emf_V_s"):
            positive(getattr(self, name), name)
        if not math.isfinite(self.friction_Nm_s) or self.friction_Nm_s < 0:
            raise ValueError("friction_Nm_s must be finite and nonnegative")
        if not math.isfinite(self.initial_output):
            raise ValueError("initial_output must be finite")
        damping = self.friction_Nm_s + self.torque_Nm_A * self.back_emf_V_s / self.resistance_ohm
        positive(damping, "derived damping")
        positive(damping / self.inertia_kg_m2, "derived rate")
        self.reset()

    def reset(self) -> None:
        self.output = self.initial_output

    def advance(self, u: float, disturbance: float, dt: float) -> None:
        positive(dt, "dt")
        finite_inputs(u, disturbance)
        damping = self.friction_Nm_s + self.torque_Nm_A * self.back_emf_V_s / self.resistance_ohm
        rate = damping / self.inertia_kg_m2
        equilibrium = (self.torque_Nm_A * u / self.resistance_ohm - disturbance) / damping
        if not math.isfinite(equilibrium):
            raise ValueError("motor equilibrium is not finite")
        self.output += (equilibrium - self.output) * (-math.expm1(-rate * dt))
