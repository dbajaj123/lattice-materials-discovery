from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AgingStep(Record):
    name: str = "age"
    temperature_c: float = Field(ge=250, le=450)
    duration_h: float = Field(gt=0, le=250)
    ramp_h: float = Field(default=0, ge=0, le=10)
    purpose: Literal["precipitate", "coarsening_resistance"] = "precipitate"


class Candidate(Record):
    name: str = Field(min_length=1, max_length=100)
    # Explicit atomic fractions; never silently interpret wt% or at%.
    composition_at_fraction: dict[str, float]
    steps: list[AgingStep] = Field(min_length=1, max_length=4)
    initial_state: Literal["assumed_supersaturated_fcc"] = "assumed_supersaturated_fcc"
    hypothesis: str = ""
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_composition_and_route(self):
        c = self.composition_at_fraction
        if set(c) - {"AL", "SC", "ZR"} or "AL" not in c or "SC" not in c:
            raise ValueError("Supported screening domain: AL + SC, optionally ZR")
        if any(not 0 <= x <= 1 for x in c.values()) or abs(sum(c.values()) - 1) > 1e-8:
            raise ValueError("Atomic fractions must be nonnegative and sum to one")
        if not 0.0003 <= c["SC"] <= 0.003:
            raise ValueError("Sc screening bounds are 0.03–0.30 at.% (not validated bounds)")
        if not 0 <= c.get("ZR", 0) <= 0.002:
            raise ValueError("Zr screening bounds are 0–0.20 at.%")
        if sum(s.duration_h + s.ramp_h for s in self.steps) > 500:
            raise ValueError("Route exceeds 500 hours")
        if self.steps[0].ramp_h != 0:
            raise ValueError("First aging step starts at its setpoint; initial heat-up is not simulated")
        if any(s.ramp_h == 0 and s.temperature_c != p.temperature_c
               for p, s in zip(self.steps, self.steps[1:])):
            raise ValueError("Temperature changes require an explicit nonzero ramp_h")
        return self

    @property
    def total_hours(self):
        return sum(s.duration_h + s.ramp_h for s in self.steps)

    @property
    def is_ternary(self):
        return self.composition_at_fraction.get("ZR", 0) > 0


class SimulationSettings(Record):
    gamma_j_m2: float = Field(default=0.1, ge=0.05, le=0.2)
    diffusivity_multiplier: float = Field(default=1, gt=0, le=10)
    bins: int = Field(default=150, ge=75, le=600)
    max_dt_fraction: float = Field(default=0.02, gt=0, le=0.1)


def example_candidate() -> Candidate:
    return Candidate(name="Al–0.20 at.% Sc reference", composition_at_fraction={"AL": 0.998, "SC": 0.002},
                     steps=[AgingStep(temperature_c=400, duration_h=4)],
                     hypothesis="Reproduce the upstream Al–Sc strength example over a shorter aging window.",
                     evidence_ids=["kawin-strength-example"])


def schedule(candidate: Candidate):
    """Return continuous knots in hours and Kelvin, plus exact step-end times."""
    times = [0.0]
    temperatures = [candidate.steps[0].temperature_c + 273.15]
    ends = []
    t = 0.0
    for step in candidate.steps:
        if step.ramp_h:
            t += step.ramp_h
            times.append(t)
            temperatures.append(step.temperature_c + 273.15)
        t += step.duration_h
        times.append(t)
        temperatures.append(step.temperature_c + 273.15)
        ends.append(t)
    return times, temperatures, ends
