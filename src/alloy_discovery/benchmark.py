"""Source-linked experimental consistency check without fitting to the test points."""
import json
import math
from pathlib import Path
from .schema import Candidate, AgingStep
from .runner import run_candidate
from .simulator import DATA, save_json

ATOMIC_MASS = {"AL":26.9815385,"SC":44.955908,"ZR":91.224}


def weight_to_atomic_sc(weight_percent):
    w = weight_percent/100
    return (w/ATOMIC_MASS["SC"])/(w/ATOMIC_MASS["SC"]+(1-w)/ATOMIC_MASS["AL"])


def atomic_to_weight_percent(composition):
    denom = sum(x*ATOMIC_MASS[e] for e,x in composition.items())
    return {e:100*x*ATOMIC_MASS[e]/denom for e,x in composition.items()}


def literature_benchmark(root, timeout_s=180):
    source = json.loads((DATA/"marquis-2001.json").read_text())
    results = []
    report = {"kind":"literature_consistency_check", "calibrated":False, "independent_holdout":False,
              "source":source, "results":results,
              "interpretation":"Compare fixed upstream parameters with reported experimental endpoints; no parameter fitting, probability calibration or family-wide validation is performed."}
    for observation in source["observations"]:
        x = weight_to_atomic_sc(observation["sc_weight_percent"])
        candidate = Candidate(name=f"Marquis 2001 · {observation['sc_weight_percent']} wt.% Sc",
                              composition_at_fraction={"AL":1-x,"SC":x},
                              steps=[AgingStep(temperature_c=300,duration_h=72)],
                              hypothesis="Test fixed-model agreement with Table 1; preparation is assumed, not simulated.",
                              evidence_ids=[source["source_id"]])
        print(f"Experimental comparison: {candidate.name}",flush=True)
        result = run_candidate(candidate,root,timeout_s=timeout_s)
        row = {"observation":observation,"candidate":candidate.model_dump(),"evaluation_status":result["status"],"run_id":result.get("run_id")}
        if result["status"] == "completed":
            metrics = result["metrics"]
            row.update(predicted_radius_nm=metrics["final_radius_nm"],predicted_density_m3=metrics["final_number_density_m3"],
                       radius_absolute_error_nm=abs(metrics["final_radius_nm"]-observation["radius_nm"]),
                       density_ratio=metrics["final_number_density_m3"]/observation["density_m3"],
                       radius_within_reported_range=abs(metrics["final_radius_nm"]-observation["radius_nm"]) <= observation["radius_reported_error_nm"])
        results.append(row)
        save_json(Path(root)/"experimental-comparison.json",report)
    return report


def synthesis_dossier(candidate):
    source = json.loads((DATA/"marquis-2001.json").read_text())
    weight = atomic_to_weight_percent(candidate.composition_at_fraction)
    in_range = not candidate.is_ternary and 0.1 <= weight["SC"] <= 0.3
    return {"candidate":candidate.model_dump(),"composition_weight_percent":weight,
            "status":"analogue_route_requires_validation" if in_range else "outside_precedent_composition_range",
            "source": {k:source[k] for k in ["url","doi","methods_location"]},
            "source_composition_range_sc_weight_percent":[0.1,0.3],
            "preparation_precedent":[dict(step,evidence="reported_for_source_alloys",simulated=False) for step in source["preparation"][:-1]],
            "proposed_aging_steps":[dict(step.model_dump(),evidence="agent_proposal_not_source_recipe") for step in candidate.steps],
            "required_checks":["Verify alloy chemistry and relevant phase boundaries for the proposed composition.",
                               "Establish that the prepared material reaches the assumed supersaturated state.",
                               "Account for specimen geometry, deformation and quench history.",
                               "Measure phase identity, size distribution and mechanical response against a matched baseline."],
            "limitations":source["limitations"],
            "claim":"A literature analogue supplies a plausible starting route, not proof that this proposed material can be made with the predicted properties."}
