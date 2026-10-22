"""Grades never promote numerical success to experimental or novelty certainty."""
from __future__ import annotations
import numpy as np


def numerical_checks(time_s, temperature_k, composition, volume_fraction, radius_m,
                     density_m3, solute_in_precipitates, initial_composition,
                     expected_end_s, psd):
    arrays = [time_s, temperature_k, composition, volume_fraction, radius_m,
              density_m3, solute_in_precipitates, psd]
    finite = all(np.isfinite(a).all() for a in arrays)
    f = np.sum(volume_fraction, axis=1)
    # Kawin volume convention, checked independently from its composition update.
    recovered = composition * (1-f[:, None]) + np.sum(solute_in_precipitates, axis=1)
    residual = float(np.max(np.abs(recovered - np.asarray(initial_composition)))) if finite else None
    checks = {
        "finite_outputs": finite,
        "nonnegative_populations": bool(np.all(np.asarray(psd) >= -1e-12) and np.all(density_m3 >= 0)),
        "physical_fractions": bool(np.all(volume_fraction >= -1e-10) and np.all(f <= 1+1e-10)
                                   and np.all(composition >= 0) and np.all(np.sum(composition, axis=1) <= 1)),
        "nonnegative_radii": bool(np.all(radius_m >= 0)),
        "monotonic_time": bool(np.all(np.diff(time_s) > 0)),
        "reached_end_time": bool(np.isclose(time_s[-1], expected_end_s, rtol=1e-7, atol=1e-5)),
        "internal_solute_balance": residual is not None and residual < 1e-7,
    }
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks,
            "max_solute_balance_residual_at_fraction": residual,
            "discretization_convergence": "not_checked"}


def evidence_gates(ternary=False):
    return {
        "novelty": {"status": "unresolved", "reason": "Known alloy family; composition/process novelty requires a scoped literature and patent review. Exact decimal differences are not discoveries."},
        "experimental_validation": {"status": "unvalidated", "reason": "No held-out experimental calibration has been completed."},
        "synthesis_route": {"status": "conditional", "reason": "Aging starts from an assumed supersaturated FCC state. Melting, homogenization, solution treatment and quenching remain unverified."},
        "model_applicability": {"status": "exploratory" if ternary else "reference_parameters",
                               "reason": "Restricted phase database; no liquid phase. Ternary kinetics and strength are not inferred from binary fits." if ternary else "Upstream Al–Sc example parameters; screening bounds are not experimentally validated bounds."},
    }


def discovery_status(result):
    gates = result.get("evidence", {})
    if result.get("status") != "completed" or result.get("numerical", {}).get("status") != "pass":
        return "not_eligible"
    required = {"novelty": "reviewed_no_match", "experimental_validation": "validated_domain",
                "synthesis_route": "supported", "model_applicability": "validated_domain"}
    if any(gates.get(k, {}).get("status") != v for k,v in required.items()):
        return "screening_candidate_only"
    return "candidate_for_experimental_testing"
