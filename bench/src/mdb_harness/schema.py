from __future__ import annotations

import hashlib
import json
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymatgen.core import Element, Structure


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Crystal(StrictModel):
    lattice: list[list[float]]
    species: list[str] = Field(min_length=1, max_length=128)
    frac_coords: list[list[float]]

    @model_validator(mode="after")
    def valid_geometry(self):
        lattice = np.asarray(self.lattice)
        coords = np.asarray(self.frac_coords)
        if lattice.shape != (3, 3) or coords.shape != (len(self.species), 3):
            raise ValueError("Expected a 3x3 lattice and one fractional xyz per atom")
        if not np.isfinite(lattice).all() or not np.isfinite(coords).all():
            raise ValueError("Nonfinite geometry")
        if np.linalg.det(lattice) <= 1e-3:
            raise ValueError("Cell must have positive, nonzero volume in angstrom cubed")
        for species in self.species:
            Element(species)
        s = self.structure()
        if len(s) > 1:
            distances = s.distance_matrix + np.eye(len(s)) * 1e6
            if float(distances.min()) < 0.5:
                raise ValueError("Atoms closer than 0.5 angstrom; check units and sites")
        return self

    def structure(self) -> Structure:
        return Structure(self.lattice, self.species, self.frac_coords)

    @classmethod
    def from_structure(cls, s: Structure):
        return cls(lattice=s.lattice.matrix.tolist(), species=[x.specie.symbol for x in s],
                   frac_coords=s.frac_coords.tolist())

    def digest(self) -> str:
        # Exact request identity only. Structural equivalence uses StructureMatcher.
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


class SynthesisStep(StrictModel):
    operation: str = Field(min_length=3)
    target_phase_or_state: str = Field(min_length=1)
    phase_formation_mechanism: str = ""
    temperature_c: float | None = Field(default=None, ge=-273.15, le=5000)
    duration_minutes: float | None = Field(default=None, gt=0)
    pressure_pa: float | None = Field(default=None, gt=0)
    on_device_wafer: bool = True
    precursors: list[str] = Field(default_factory=list)
    equipment: str = ""
    atmosphere: str = ""
    evidence_urls: list[str] = Field(default_factory=list)
    characterization: str = ""


class Proposal(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    hypothesis: str = Field(min_length=10)
    crystal: Crystal
    synthesis: list[SynthesisStep] = Field(default_factory=list, max_length=30)
    closest_prior_art: list[str] = Field(default_factory=list)
    # Agent-reported property values and self-assigned novelty/verdicts are forbidden.


class PhysicsResult(StrictModel):
    status: Literal["partial", "complete", "failed"]
    backend: str
    input_digest: str
    relaxed: Crystal | None = None
    converged: bool = False
    minimum_phonon_thz: float | None = None
    youngs_gpa: float | None = None
    shear_gpa: float | None = None
    kappa_w_mk: float | None = None
    epsilon_static: float | None = None
    epsilon_infinity: float | None = None
    warnings: list[str] = Field(default_factory=list)
    artifacts: dict = Field(default_factory=dict)


class Gate(StrictModel):
    name: str
    status: Literal["pass", "fail", "unknown"]
    reason: str


def physics_gates(result: PhysicsResult) -> list[Gate]:
    checks = [
        ("relaxation", result.converged if result.status != "failed" else False, bool, "Converged structure relaxation"),
        ("dynamic_stability", result.minimum_phonon_thz, lambda x: x >= -1.0, "Minimum sampled phonon frequency >= -1 THz"),
        ("thermal_conductivity", result.kappa_w_mk, lambda x: x > 20, "Thermal conductivity > 20 W/(m K)"),
        ("static_dielectric", result.epsilon_static, lambda x: 1 <= x < 10, "Static dielectric constant >= 1 and < 10; high-frequency epsilon is not interchangeable"),
        ("youngs_modulus", result.youngs_gpa, lambda x: x >= 20, "Young's modulus >= 20 GPa"),
        ("shear_modulus", result.shear_gpa, lambda x: x >= 6, "Shear modulus >= 6 GPa"),
    ]
    gates=[Gate(name=n, status="unknown" if v is None else "pass" if test(v) else "fail", reason=reason)
            for n, v, test, reason in checks]
    if result.minimum_phonon_thz is not None and -1<=result.minimum_phonon_thz<-.1:
        gates[1]=Gate(name='dynamic_stability',status='unknown',reason='Small imaginary modes need convergence checks; not credited as stable')
    return gates


def synthesis_checks(proposal: Proposal, max_wafer_c: float = 400) -> list[dict]:
    """Deterministic completeness checks, never a scientific plausibility verdict."""
    result = []
    for i, step in enumerate(proposal.synthesis):
        missing = [k for k in ("phase_formation_mechanism", "temperature_c", "duration_minutes",
                              "precursors", "equipment", "atmosphere", "evidence_urls", "characterization")
                   if getattr(step, k) is None or getattr(step, k) == "" or getattr(step, k) == []]
        conflicts = []
        if step.on_device_wafer and step.temperature_c is not None and step.temperature_c > max_wafer_c:
            conflicts.append(f"On-wafer temperature exceeds local {max_wafer_c:g} C constraint")
        result.append({"step": i + 1, "operation": step.operation, "missing_fields": missing,
                       "conflicts": conflicts, "status": "fail" if conflicts else "unknown",
                       "reason": "Mechanism, citations, equipment and phase selectivity require independent review"})
    return result
