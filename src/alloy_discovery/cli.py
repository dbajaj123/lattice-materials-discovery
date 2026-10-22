from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import traceback

from .schema import Candidate, SimulationSettings, example_candidate


def main():
    parser = argparse.ArgumentParser(description="Evidence-aware alloy discovery harness")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("example", help="Write a validated reference candidate")
    p.add_argument("output", type=Path)
    p = sub.add_parser("evaluate", help="Evaluate a composition + route in an isolated real simulator")
    p.add_argument("candidate", type=Path)
    p.add_argument("--output", type=Path, default=Path("runs/evaluation"))
    p.add_argument("--timeout", type=float, default=180)
    p.add_argument("--retry-failed", action="store_true")
    p = sub.add_parser("campaign", help="Run matched random/feedback baselines and ternary screens")
    p.add_argument("--output", type=Path, default=Path("runs/initial"))
    p.add_argument("--budget", type=int, default=4)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--timeout", type=float, default=180)
    p = sub.add_parser("sensitivity", help="Parameter perturbations and resolution check, not confidence intervals")
    p.add_argument("candidate", type=Path)
    p.add_argument("--output", type=Path, default=Path("runs/sensitivity"))
    p.add_argument("--timeout", type=float, default=180)
    p = sub.add_parser("literature", help="Retrieve and cache related bibliographic records")
    p.add_argument("--output", type=Path, default=Path("runs/initial"))
    p = sub.add_parser("report", help="Export an offline interactive dashboard")
    p.add_argument("campaign", type=Path)
    p.add_argument("--output", type=Path, default=Path("runs/initial/report.html"))
    p = sub.add_parser("agent-context", help="Export instructions, candidate schema, evidence and feedback for an external reasoning agent")
    p.add_argument("--campaign", type=Path)
    p = sub.add_parser("benchmark", help="Compare fixed simulator parameters with published experimental endpoints")
    p.add_argument("--output", type=Path, default=Path("runs/initial"))
    p.add_argument("--timeout", type=float, default=180)
    p = sub.add_parser("synthesis-route", help="Attach an evidence-linked preparation analogue to a proposed aging route")
    p.add_argument("candidate", type=Path)
    p.add_argument("--output", type=Path, default=Path("runs/synthesis-route.json"))
    p = sub.add_parser("_worker")
    p.add_argument("request", type=Path)
    p.add_argument("output", type=Path)
    args = parser.parse_args()
    from .simulator import save_json
    if args.command == "example":
        save_json(args.output, example_candidate().model_dump())
    elif args.command == "_worker":
        from .simulator import evaluate
        request = json.loads(args.request.read_text())
        try:
            result = evaluate(Candidate.model_validate(request["candidate"]), SimulationSettings.model_validate(request["settings"]),
                              on_step=lambda progress: save_json(args.output.with_name("progress.json"), progress))
        except Exception as exc:
            traceback.print_exc()
            result = {"status": "failed", "candidate": request.get("candidate"), "error": f"{type(exc).__name__}: {exc}",
                      "metrics": None, "trace": None, "steps": [], "evidence": {}, "numerical": {"status": "indeterminate"},
                      "discovery_status": "not_eligible"}
            progress_path = args.output.with_name("progress.json")
            if progress_path.exists():
                progress = json.loads(progress_path.read_text())
                result.update(steps=progress["completed_steps"], evidence=progress["evidence"],
                              provenance=progress["provenance"], equilibrium=progress["equilibrium"], partial_progress=True)
        save_json(args.output, result)
    elif args.command == "evaluate":
        from .runner import run_candidate
        candidate = Candidate.model_validate_json(args.candidate.read_text())
        result = run_candidate(candidate, args.output, timeout_s=args.timeout, retry_failed=args.retry_failed)
        save_json(args.output/"result.json", result)
        print(json.dumps({k:result.get(k) for k in ["status","run_id","metrics","discovery_status","error"]}, indent=2))
        if result["status"] == "failed":
            sys.exit(1)
    elif args.command == "campaign":
        if not 1 <= args.budget <= 100:
            parser.error("budget must be between 1 and 100")
        from .search import campaign
        from .report import export_report
        campaign(args.output, args.budget, args.seed, args.timeout)
        export_report(args.output/"campaign.json", args.output/"report.html")
        print(f"Report: {(args.output/'report.html').resolve()}")
    elif args.command == "sensitivity":
        from .runner import sensitivity
        candidate = Candidate.model_validate_json(args.candidate.read_text())
        result = sensitivity(candidate, args.output, args.timeout)
        save_json(args.output/"sensitivity.json", result)
        print(json.dumps({k:v for k,v in result.items() if k not in ["scenarios","candidate"]}, indent=2))
    elif args.command == "literature":
        from .literature import retrieve
        result = retrieve(args.output)
        save_json(args.output/"literature.json", result)
        print(json.dumps({"searches":len(result["searches"]), "records":sum(len(r["works"]) for r in result["searches"]),
                          "novelty_status":result["novelty_status"], "errors":[r.get("error") for r in result["searches"] if r["status"] == "error"]}, indent=2))
    elif args.command == "report":
        from .report import export_report
        export_report(args.campaign, args.output)
    elif args.command == "benchmark":
        from .benchmark import literature_benchmark
        result = literature_benchmark(args.output,args.timeout)
        print(json.dumps(result["results"],indent=2))
    elif args.command == "synthesis-route":
        from .benchmark import synthesis_dossier
        result = synthesis_dossier(Candidate.model_validate_json(args.candidate.read_text()))
        save_json(args.output,result)
        print(f"{result['status']}: {args.output.resolve()}")
    elif args.command == "agent-context":
        from .simulator import DATA
        context = {"objective": "Find a useful new alloy composition AND a plausible supported synthesis route.",
                   "candidate_schema": Candidate.model_json_schema(),
                   "instructions": ["Propose Candidate JSON only; include a falsifiable hypothesis and evidence IDs.",
                                    "Binary Al-Sc is the commissioning benchmark, not a novel family.",
                                    "Ternary Al-Sc-Zr is thermodynamic-screen-only until mobility and strength models are validated.",
                                    "Novel decimal ratios do not establish novelty; evaluate prior composition ranges and process families.",
                                    "Prefer uncertainty-reducing actions when model applicability or synthesis evidence is missing.",
                                    "Never report simulated precipitation contribution as measured total yield strength.",
                                    "After proposing, use evaluate; read the full step assessments and revise the proposal."],
                   "evidence": json.loads((DATA/"evidence.json").read_text()),
                   "feedback": json.loads(args.campaign.read_text()) if args.campaign else None}
        print(json.dumps(context, indent=2))


if __name__ == "__main__":
    main()
