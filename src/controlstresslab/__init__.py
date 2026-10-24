"""Controller stress tests. Demo parameters are synthetic, not measured."""

__version__ = "0.1.2"

from .controllers import PID
from .models import DCMotor, FirstOrder
from .extended_models import InductiveDCMotor, MassSpringDamper
from .extended_controllers import LinearADRC, TwoDOFPID
from .signals import SampledSignal, waveform
from .simulation import Scenario, StepSignal, simulate

__all__ = ["PID", "DCMotor", "FirstOrder", "Scenario", "StepSignal", "simulate",
           "InductiveDCMotor", "MassSpringDamper", "LinearADRC", "TwoDOFPID", "SampledSignal", "waveform"]
