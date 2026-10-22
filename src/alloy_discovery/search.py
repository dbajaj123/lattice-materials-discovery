"""Small reproducible baseline and feedback search, plus external-agent proposals."""
from __future__ import annotations
import random
from pathlib import Path

from .schema import Candidate, AgingStep, example_candidate
from .runner import run_candidate
from .simulator import save_json


def candidate_at(sc, temp, hours, name, zr=0):
    c = {"AL": 1-sc-zr, "SC": sc}
    if zr:
        c["ZR"] = zr
    return Candidate(name=name, composition_at_fraction=c,
                     steps=[AgingStep(temperature_c=temp, duration_h=hours)],
                     hypothesis="Explore the composition–processing tradeoff within the restricted Al–Sc–Zr model domain.")


def pareto_indices(results):
    valid = [(i,r["metrics"]) for i,r in enumerate(results)
             if r["status"] == "completed" and r.get("numerical",{}).get("status") == "pass" and r.get("metrics")]
    front = []
    for i,a in valid:
        va = [-a["final_strength_increment_mpa"], a["sc_at_percent"], a["processing_hours"]]
        dominated = False
        for j,b in valid:
            vb = [-b["final_strength_increment_mpa"], b["sc_at_percent"], b["processing_hours"]]
            if i != j and all(x<=y for x,y in zip(vb,va)) and any(x<y for x,y in zip(vb,va)):
                dominated = True
                break
        if not dominated:
            front.append(i)
    return front


def feedback_candidate(results, rng, index):
    completed = [r for r in results if r.get("metrics") and r["status"] == "completed"]
    if not completed:
        return candidate_at(0.001, 350, 4, f"feedback-{index}")
    # Explicit heuristic; this is not an LLM and not a scientific success score.
    best = max(completed, key=lambda r: r["metrics"]["final_strength_increment_mpa"])
    c = Candidate.model_validate(best["candidate"])
    m = best["metrics"]
    sc = min(0.003, max(0.0003, c.composition_at_fraction["SC"]*rng.choice([0.75,1,1.25])))
    t = c.steps[0].temperature_c
    h = c.steps[0].duration_h
    if m["peak_time_h"] < 0.8*h:
        h = max(0.1, m["peak_time_h"])
        t = max(250, t-25)
        reason = "Earlier strengthening peak suggests overaging; reduce hold or temperature."
    else:
        t = min(450, max(250, t+rng.choice([-25,25])))
        h = min(48, max(0.1, h*rng.choice([0.5,1.5])))
        reason = "Explore temperature and duration around the strongest modeled candidate."
    proposal = candidate_at(sc,t,h,f"feedback-{index}")
    proposal.hypothesis = reason
    return proposal


def campaign(root: Path, budget=4, seed=7, timeout_s=180):
    """Equal proposal counts for a random and transparent feedback baseline."""
    root = Path(root)
    report = {"objective": "Discover a useful new alloy composition with a supported processing route",
              "stage": "simulator commissioning and exploratory screening", "seed": seed,
              "budget_per_method": budget, "methods": {}, "ternary_screens": [],
              "confirmed_novel_materials": 0,
              "claim": "No material discovery or experimental success has been established."}
    for method in ["random", "feedback_heuristic"]:
        rng = random.Random(seed)
        rows = []
        report["methods"][method] = rows
        for i in range(budget):
            if i == 0:
                proposal = example_candidate()
            elif method == "feedback_heuristic":
                proposal = feedback_candidate(rows, rng, i)
            else:
                proposal = candidate_at(rng.choice([0.0005,0.001,0.0015,0.002]),
                                        rng.choice([300,325,350,375,400]),
                                        rng.choice([0.5,1,4,12]),f"random-{i}")
            print(f"{method} proposal {i+1}/{budget}: {proposal.name}", flush=True)
            result = run_candidate(proposal, root, timeout_s=timeout_s)
            result["proposal_index"] = i+1
            rows.append(result)
            save_json(root/"campaign.json", report)
    for sc,zr in [(0.0005,0.0005),(0.001,0.0005),(0.0005,0.001)]:
        proposal = candidate_at(sc,350,4,f"Al-{sc*100:.3f}Sc-{zr*100:.3f}Zr at.%",zr)
        print(f"Ternary equilibrium screen: {proposal.name}", flush=True)
        report["ternary_screens"].append(run_candidate(proposal, root, timeout_s=timeout_s))
        save_json(root/"campaign.json", report)
    report["pareto"] = {method: pareto_indices(rows) for method,rows in report["methods"].items()}
    save_json(root/"campaign.json", report)
    return report
