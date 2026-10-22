from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
import warnings

os.environ.setdefault("MPLCONFIGDIR", "/tmp/materials-discovery-mpl")
import numpy as np

from .schema import Candidate, SimulationSettings, schedule
from .grading import numerical_checks, evidence_gates, discovery_status

DATA = Path(__file__).parent / "data"
DATABASE = DATA / "AlScZr.tdb"


def provenance():
    return {"backend": "Kawin KWN + pycalphad", "kawin_version": importlib.metadata.version("kawin"),
            "pycalphad_version": importlib.metadata.version("pycalphad"),
            "database_sha256": hashlib.sha256(DATABASE.read_bytes()).hexdigest(),
            "database_source": json.loads((DATA / "database-provenance.json").read_text()),
            "code_version": "0.1.0", "uncertainty_calibrated": False}


def equilibrium_screen(candidate: Candidate):
    """Restricted phase equilibrium, not a complete stability or synthesis verdict."""
    from pycalphad import Database, equilibrium, variables as v
    db = Database(str(DATABASE))
    components = [e for e,x in candidate.composition_at_fraction.items() if x > 0] + ["VA"]
    points = []
    for temperature in sorted({s.temperature_c for s in candidate.steps}):
        conditions = {v.N: 1, v.P: 101325, v.T: temperature + 273.15}
        conditions.update({v.X(e): x for e,x in candidate.composition_at_fraction.items() if e != "AL" and x > 0})
        eq = equilibrium(db, components, sorted(db.phases), conditions)
        fractions = {}
        for phase, amount in zip(np.asarray(eq.Phase).ravel(), np.asarray(eq.NP).ravel()):
            if phase and np.isfinite(amount):
                fractions[str(phase)] = fractions.get(str(phase), 0) + float(amount)
        if not fractions or not np.isclose(sum(fractions.values()), 1, atol=1e-6):
            raise RuntimeError("Equilibrium calculation did not return normalized phase amounts")
        points.append({"temperature_c": temperature, "phase_mole_fractions": fractions})
    return {"status": "restricted_phase_screen", "points": points,
            "available_phases": sorted(db.phases),
            "limitation": "Only FCC_A1, AL3SC and AL3ZR are included. No liquid or exhaustive competing-phase assessment. Equilibrium fractions are mole fractions, not KWN volume fractions."}


def _make_binary_model(candidate, settings):
    from kawin.thermo import BinaryThermodynamics
    from kawin.precipitation import MatrixParameters, PrecipitateParameters, PrecipitateModel, TemperatureParameters
    from kawin.precipitation.coupling import (
        StrengthModel, DislocationParameters, CoherencyContribution,
        ModulusContribution, APBContribution, InterfacialContribution,
    )
    therm = BinaryThermodynamics(str(DATABASE), ["AL", "SC"], ["FCC_A1", "AL3SC"])
    therm.setGuessComposition(0.24)
    therm.setDiffusivity(lambda T: settings.diffusivity_multiplier*1.9e-4*np.exp(-164000/(8.314*T)), "FCC_A1")
    matrix = MatrixParameters(["SC"])
    matrix.initComposition = candidate.composition_at_fraction["SC"]
    matrix.volume.setVolume((0.409e-9)**3, "VA", 4)
    precipitate = PrecipitateParameters("AL3SC")
    precipitate.gamma = settings.gamma_j_m2
    precipitate.volume.setVolume((0.4196e-9)**3, "VA", 4)
    precipitate.nucleation.setNucleationType("bulk")
    strength = StrengthModel(precipitate, [
        CoherencyContribution(eps=2/3*0.0125), ModulusContribution(Gp=67.9e9),
        APBContribution(yAPB=0.5), InterfacialContribution(gamma=settings.gamma_j_m2),
    ], DislocationParameters(G=25.4e9, b=0.286e-9, nu=0.34))
    times, temperatures, _ = schedule(candidate)
    model = PrecipitateModel(matrix, precipitate, therm, TemperatureParameters(times, temperatures))
    model.setPBMParameters(cMin=1e-10, cMax=1e-8, bins=settings.bins,
                           minBins=settings.bins, maxBins=settings.bins*2)
    model.addCouplingModel(strength)
    return model, strength


def evaluate(candidate: Candidate, settings: SimulationSettings | None = None, on_step=None):
    settings = settings or SimulationSettings()
    start = time.monotonic()
    result = {"candidate": candidate.model_dump(), "settings": settings.model_dump(),
              "provenance": provenance(), "evidence": evidence_gates(candidate.is_ternary)}
    result["equilibrium"] = equilibrium_screen(candidate)
    if candidate.is_ternary:
        result.update(status="partial", discovery_status="not_eligible",
                      next_action="Acquire and validate multicomponent diffusivities/mobilities, precipitate partitioning and mechanical parameters before kinetic ranking.",
                      numerical={"status": "indeterminate", "reason": "Kinetics not executed"},
                      steps=[{"name": s.name, "status": "indeterminate", "reason": "Ternary kinetics unsupported; equilibrium is not a time-dependent route test."} for s in candidate.steps],
                      metrics=None, trace=None, wall_seconds=time.monotonic()-start)
        return result
    model, strength = _make_binary_model(candidate, settings)
    _, _, ends = schedule(candidate)
    step_results = []
    snapshots = []
    all_warnings = []
    for index, (step, end_h) in enumerate(zip(candidate.steps, ends)):
        before_time = float(model.currentTime)
        before_density = float(model.data.precipitateDensity[-1, 0])
        before_radius = float(model.data.Ravg[-1, 0])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # solve takes an increment; the SAME model and PSD continue through steps.
            model.solve(end_h*3600-model.currentTime, maxDtFrac=settings.max_dt_fraction, verbose=True, vIt=5000)
        all_warnings.extend(str(w.message) for w in caught)
        data = model.data
        numeric = numerical_checks(data.time, data.temperature, data.composition, data.volFrac,
                                   data.Ravg, data.precipitateDensity, data.fconc,
                                   [candidate.composition_at_fraction["SC"]], end_h*3600, model.PBM[0].PSD)
        sigma = strength.totalStrength(model)
        sigma_before = float(np.interp(before_time, data.time, sigma)/1e6)
        increment = float(sigma[-1]/1e6)
        # Process grades describe observed changes; threshold choice is explicit.
        if step.purpose == "coarsening_resistance":
            achieved = sigma_before > 0 and increment >= 0.9*sigma_before
            objective = "Retain at least 90% of pre-step predicted precipitation strengthening"
        else:
            achieved = float(data.volFrac[-1,0]) > 1e-5 and increment >= sigma_before
            objective = "Form precipitates and avoid reducing the pre-step strengthening estimate"
        step_results.append({"index": index, "name": step.name, "start_h": before_time/3600,
                             "end_h": end_h, "status": numeric["status"], "numerical": numeric,
                             "purpose": objective, "objective_met_in_model": achieved,
                             "experimental_certainty": "uncalibrated", "state_preserved": index > 0,
                             "start_density_m3": before_density, "start_radius_nm": before_radius*1e9,
                             "end_radius_nm": float(data.Ravg[-1,0]*1e9),
                             "end_volume_fraction": float(data.volFrac[-1,0]),
                             "strength_increment_mpa": increment})
        snapshots.append({"step": index, "time_h": end_h, "radius_nm": (model.PBM[0].PSDsize*1e9).tolist(),
                          "number_per_bin_m3": model.PBM[0].PSD.tolist()})
        if on_step is not None:
            on_step({"status": "running", "candidate": candidate.model_dump(),
                     "completed_steps": step_results.copy(), "latest_size_distribution": snapshots[-1],
                     "provenance": result["provenance"], "evidence": result["evidence"],
                     "equilibrium": result["equilibrium"]})
        if numeric["status"] != "pass":
            break
    data = model.data
    sigma = strength.totalStrength(model)/1e6
    # Keep extrema and step boundaries as well as a uniform sample for display.
    indices = np.unique(np.r_[np.linspace(0, len(data.time)-1, min(500,len(data.time))).astype(int),
                               np.argmax(sigma), [np.argmin(abs(data.time-e*3600)) for e in ends]])
    result.update(status="completed" if len(step_results) == len(candidate.steps) and all(s["status"] == "pass" for s in step_results) else "failed",
                  steps=step_results, numerical=step_results[-1]["numerical"],
                  warnings=sorted(set(all_warnings)),
                  metrics={"final_strength_increment_mpa": float(sigma[-1]),
                           "peak_strength_increment_mpa": float(np.max(sigma)),
                           "peak_time_h": float(data.time[np.argmax(sigma)]/3600),
                           "final_radius_nm": float(data.Ravg[-1,0]*1e9),
                           "final_volume_fraction": float(data.volFrac[-1,0]),
                           "final_number_density_m3": float(data.precipitateDensity[-1,0]),
                           "sc_at_percent": 100*candidate.composition_at_fraction["SC"],
                           "processing_hours": candidate.total_hours},
                  trace={"time_h": (data.time[indices]/3600).tolist(),
                         "temperature_c": (data.temperature[indices]-273.15).tolist(),
                         "radius_nm": (data.Ravg[indices,0]*1e9).tolist(),
                         "volume_fraction": data.volFrac[indices,0].tolist(),
                         "number_density_m3": data.precipitateDensity[indices,0].tolist(),
                         "matrix_sc_at_percent": (data.composition[indices,0]*100).tolist(),
                         "strength_increment_mpa": sigma[indices].tolist(), "size_distributions": snapshots},
                  wall_seconds=time.monotonic()-start,
                  strength_interpretation="Precipitation contribution only; not measured or total alloy yield strength. Other properties are unassessed.")
    result["discovery_status"] = discovery_status(result)
    return result


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # JSON cannot encode NaN/Inf; failed outputs must never look like valid records.
    text = json.dumps(value, indent=2, allow_nan=False)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)
