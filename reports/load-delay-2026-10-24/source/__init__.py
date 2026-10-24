"""Controller stress tests. Demo parameters are synthetic, not measured."""

__version__ = "0.1.2"

from .controllers import PID
from .models import DCMotor, FirstOrder
from .simulation import Scenario, StepSignal, simulate

__all__ = ["PID", "DCMotor", "FirstOrder", "Scenario", "StepSignal", "simulate"]
