"""Setpoint-weighted PID and sampled linear ADRC, using measurement only."""

from dataclasses import dataclass, field
import math

from .controllers import PID
from .models import positive


@dataclass
class TwoDOFPID(PID):
    beta: float = 0.6

    def __post_init__(self):
        super().__post_init__()
        if not math.isfinite(self.beta) or not 0 <= self.beta <= 1:
            raise ValueError("beta must lie in [0,1]")

    def command(self, reference, measurement, dt):
        requested = super().command(reference, measurement, dt)
        self._requested = requested + self.kp*(self.beta-1)*reference
        return self._requested


@dataclass
class LinearADRC:
    """Euler ESO, bandwidth feedback, previous applied input, relative degree 1/2.

    No feedforward of true disturbance, velocity, acceleration or current.
    wo*dt <= .2 is an implementation sampling guard, not a stability theorem.
    """
    relative_degree: int = 1
    b0: float = 1.0
    control_bandwidth: float = 2.5
    observer_bandwidth: float = 10.0
    _z1: float = field(default=0.0, init=False, repr=False)
    _z2: float = field(default=0.0, init=False, repr=False)
    _z3: float = field(default=0.0, init=False, repr=False)
    _last_applied: float = field(default=0.0, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        if isinstance(self.relative_degree, bool) or self.relative_degree not in (1, 2):
            raise ValueError("relative_degree must be 1 or 2")
        positive(self.control_bandwidth, "control_bandwidth")
        positive(self.observer_bandwidth, "observer_bandwidth")
        if not math.isfinite(self.b0) or self.b0 == 0:
            raise ValueError("b0 must be finite and nonzero")

    def reset(self):
        self._z1 = self._z2 = self._z3 = self._last_applied = 0.0
        self._initialized = False

    def command(self, reference, measurement, dt):
        positive(dt, "dt")
        if dt*self.observer_bandwidth > 0.2 + 1e-14:
            raise ValueError("observer bandwidth requires a smaller sample period")
        if not all(math.isfinite(v) for v in (reference, measurement)):
            raise ValueError("reference and measurement must be finite")
        if not self._initialized:
            self._z1, self._initialized = measurement, True
        z1, z2, z3 = self._z1, self._z2, self._z3
        error, wo, wc = measurement-z1, self.observer_bandwidth, self.control_bandwidth
        if self.relative_degree == 1:
            self._z1 = z1 + dt*(z2+self.b0*self._last_applied+2*wo*error)
            self._z2 = z2 + dt*wo**2*error
            return (wc*(reference-self._z1)-self._z2)/self.b0
        self._z1 = z1 + dt*(z2+3*wo*error)
        self._z2 = z2 + dt*(z3+self.b0*self._last_applied+3*wo**2*error)
        self._z3 = z3 + dt*wo**3*error
        return (wc**2*(reference-self._z1)-2*wc*self._z2-self._z3)/self.b0

    def observe_applied(self, applied):
        if not math.isfinite(applied):
            raise ValueError("applied input must be finite")
        self._last_applied = applied
