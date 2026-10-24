"""Two-state teaching models with analytic held-input transitions (stdlib only)."""

from dataclasses import dataclass, field
import math

from .models import finite_inputs, positive


def transition_2x2(a, b, c, d, dt):
    """exp(A*dt) for a stable real 2x2 A, including repeated/complex poles."""
    mean = (a+d)/2
    discriminant = ((a-d)/2)**2 + b*c
    if abs(discriminant) < 1e-24:
        g, f = math.exp(mean*dt), math.exp(mean*dt)*dt
    elif discriminant > 0:
        root = math.sqrt(discriminant)
        plus, minus = math.exp((mean+root)*dt), math.exp((mean-root)*dt)
        g, f = (plus+minus)/2, (plus-minus)/(2*root)
    else:
        root = math.sqrt(-discriminant)
        g, f = math.exp(mean*dt)*math.cos(root*dt), math.exp(mean*dt)*math.sin(root*dt)/root
    return g+f*(a-mean), f*b, f*c, g+f*(d-mean)


def held_state(a, b, c, d, f1, f2, x1, x2, dt):
    determinant = a*d-b*c
    e1, e2 = (b*f2-d*f1)/determinant, (c*f1-a*f2)/determinant
    if not all(math.isfinite(v) for v in (e1, e2)):
        raise ValueError("nonfinite held-input equilibrium")
    aa, ab, ac, ad = transition_2x2(a, b, c, d, dt)
    return e1+aa*(x1-e1)+ab*(x2-e2), e2+ac*(x1-e1)+ad*(x2-e2)


@dataclass
class InductiveDCMotor:
    """J*omega'=Kt*i-b*omega-load; L*i'=u-R*i-Ke*omega."""
    inertia_kg_m2: float = 0.01
    friction_Nm_s: float = 0.001
    resistance_ohm: float = 1.0
    torque_Nm_A: float = 0.1
    back_emf_V_s: float = 0.1
    inductance_H: float = 0.2
    initial_output: float = 0.0
    initial_current_A: float = 0.0
    output: float = field(default=0.0, init=False)
    current_A: float = field(default=0.0, init=False)

    def __post_init__(self):
        for key in ("inertia_kg_m2", "resistance_ohm", "torque_Nm_A", "back_emf_V_s", "inductance_H"):
            positive(getattr(self, key), key)
        if self.friction_Nm_s < 0 or not all(math.isfinite(v) for v in (self.friction_Nm_s, self.initial_output, self.initial_current_A)):
            raise ValueError("invalid motor friction or initial state")
        self.reset()

    def reset(self):
        self.output, self.current_A = self.initial_output, self.initial_current_A

    def advance(self, u, disturbance, dt):
        positive(dt, "dt")
        finite_inputs(u, disturbance)
        j, l = self.inertia_kg_m2, self.inductance_H
        self.output, self.current_A = held_state(-self.friction_Nm_s/j, self.torque_Nm_A/j,
            -self.back_emf_V_s/l, -self.resistance_ohm/l, -disturbance/j, u/l,
            self.output, self.current_A, dt)


@dataclass
class MassSpringDamper:
    """x'=v; m*v'=u+disturbance-c*v-k*x. Output metres, inputs newtons."""
    mass_kg: float = 1.0
    damping_N_s_m: float = 0.6
    stiffness_N_m: float = 4.0
    initial_output: float = 0.0
    initial_velocity_m_s: float = 0.0
    output: float = field(default=0.0, init=False)
    velocity_m_s: float = field(default=0.0, init=False)

    def __post_init__(self):
        positive(self.mass_kg, "mass_kg")
        positive(self.stiffness_N_m, "stiffness_N_m")
        if self.damping_N_s_m < 0 or not all(math.isfinite(v) for v in (self.damping_N_s_m, self.initial_output, self.initial_velocity_m_s)):
            raise ValueError("invalid damping or initial state")
        self.reset()

    def reset(self):
        self.output, self.velocity_m_s = self.initial_output, self.initial_velocity_m_s

    def advance(self, u, disturbance, dt):
        positive(dt, "dt")
        finite_inputs(u, disturbance)
        self.output, self.velocity_m_s = held_state(0, 1, -self.stiffness_N_m/self.mass_kg,
            -self.damping_N_s_m/self.mass_kg, 0, (u+disturbance)/self.mass_kg,
            self.output, self.velocity_m_s, dt)
