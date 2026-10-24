"""Sampled PID with derivative on measurement and optional conditional integration."""

from dataclasses import dataclass, field
import math

from .models import positive


@dataclass
class PID:
    kp: float = 0.25
    ki: float = 0.8
    kd: float = 0.0
    anti_windup: bool = False
    derivative_filter_s: float = 0.03
    _integral: float = field(default=0.0, init=False, repr=False)
    _previous_measurement: float | None = field(default=None, init=False, repr=False)
    _derivative: float = field(default=0.0, init=False, repr=False)
    _pending_integral: float = field(default=0.0, init=False, repr=False)
    _error: float = field(default=0.0, init=False, repr=False)
    _requested: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.kp, self.ki, self.kd, self.derivative_filter_s)):
            raise ValueError("PID parameters must be finite")
        if min(self.kp, self.ki, self.kd, self.derivative_filter_s) < 0:
            raise ValueError("PID parameters must be nonnegative")

    def reset(self) -> None:
        self._integral = self._pending_integral = 0.0
        self._previous_measurement = None
        self._derivative = self._error = self._requested = 0.0

    def command(self, reference: float, measurement: float, dt: float) -> float:
        positive(dt, "dt")
        self._error = reference - measurement
        raw = 0.0 if self._previous_measurement is None else (measurement - self._previous_measurement) / dt
        alpha = 0.0 if self.derivative_filter_s == 0 else math.exp(-dt / self.derivative_filter_s)
        self._derivative = alpha * self._derivative + (1 - alpha) * raw
        self._previous_measurement = measurement
        self._pending_integral = self._integral + self.ki * self._error * dt
        self._requested = self.kp * self._error + self._pending_integral - self.kd * self._derivative
        return self._requested

    def observe_applied(self, applied: float) -> None:
        # Freeze integration only when error would drive the actuator further into saturation.
        further_into_limit = self._error * (self._requested - applied) > 0
        if not (self.anti_windup and further_into_limit):
            self._integral = self._pending_integral
