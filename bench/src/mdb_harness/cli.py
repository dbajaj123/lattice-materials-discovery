import argparse
import importlib.util
import json
import os
from pathlib import Path

from .engine import Engine, dump
from .release import audit_release, fetch_release
from .schema import Proposal


def main():
    parser = argparse.ArgumentParser(description="Independent Material Discovery Bench harness; not an official port")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser('fetch'); fetch.add_argument('destination', type=Path)
    audit = sub.add_parser('audit'); audit.add_argument('snapshot', type=Path); audit.add_argument('--output', type=Path, required=True); audit.add_argument('--skip-deduplication', action='store_true')
    report = sub.add_parser('report'); report.add_argument('snapshot', type=Path); report.add_argument('audit', type=Path); report.add_argument('--output', type=Path, required=True)
    screen = sub.add_parser('screen'); screen.add_argument('proposal', type=Path); screen.add_argument('--output', type=Path, required=True); screen.add_argument('--backend', choices=['none','petmad'], default='petmad'); screen.add_argument('--timeout', type=int, default=240); screen.add_argument('--elastic', action='store_true'); screen.add_argument('--thermal', action='store_true')
    worker = sub.add_parser('_physics'); worker.add_argument('proposal', type=Path); worker.add_argument('output', type=Path); worker.add_argument('--elastic', action='store_true'); worker.add_argument('--thermal', action='store_true')
    pipeline=sub.add_parser('discover'); pipeline.add_argument('action',choices=['prepare','run','report','status']); pipeline.add_argument('--config',type=Path,default=Path('discovery.json')); pipeline.add_argument('--output',type=Path,default=Path('runs/discovery'))
    sub.add_parser('doctor')
    sub.add_parser('schema')
    validation=sub.add_parser('validate');validation.add_argument('--library',type=Path,default=Path('data/reference/materials.sqlite'));validation.add_argument('--output',type=Path,required=True);validation.add_argument('--simulate',action='store_true');validation.add_argument('--cases',type=int,default=12)
    args = parser.parse_args()
    if args.command=='validate':
        from .validation import validate
        report=validate(args.library,args.output,simulate=args.simulate,cases=args.cases)
        print(json.dumps({k:v for k,v in report.items() if k not in ['tests','simulator_controls']},indent=2))
    elif args.command == 'fetch':
        print(json.dumps(fetch_release(args.destination), indent=2))
    elif args.command == 'audit':
        result = audit_release(args.snapshot, not args.skip_deduplication)
        dump(args.output, result)
        print(json.dumps({k:v for k,v in result.items() if k not in ['models','duplicate_of','invalid_structures']}, indent=2))
    elif args.command == 'report':
        from .report import create_report
        create_report(args.snapshot, json.loads(args.audit.read_text()), args.output)
        print(args.output)
    elif args.command == 'screen':
        engine = Engine(args.output, backend=args.backend, timeout=args.timeout, elastic=args.elastic,thermal=args.thermal)
        result = engine.screen(json.loads(args.proposal.read_text()))
        if result.get('candidate_id') in engine.results:
            engine.submit(result['candidate_id'])
        print(json.dumps(result, indent=2))
    elif args.command == '_physics':
        from .physics import petmad_screen
        proposal = Proposal.model_validate_json(args.proposal.read_text())
        result = petmad_screen(proposal.crystal, args.output, elastic=args.elastic,thermal=args.thermal)
        dump(args.output / 'physics.json', result.model_dump())
    elif args.command == 'doctor':
        print(json.dumps({
            'packages': {p: bool(importlib.util.find_spec(p)) for p in ['pymatgen','ase','phonopy','pet_mad','inspect_ai']},
            'credentials_present': {p: bool(os.environ.get(p)) for p in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','EXA_API_KEY','MP_API_KEY']},
            'ready_for_official_sota_comparison': False,
            'missing_official_assets': ['Repository commit and license','Exact task configuration and tensor reductions','Dielectric model weights','Thermal evaluator settings','Complete synthesis rubrics and grader configuration','Run budgets and complete baseline logs'],
        }, indent=2))
    elif args.command == 'schema':
        print(json.dumps(Proposal.model_json_schema(), indent=2))
    elif args.command == 'discover':
        from .campaign import load_config,prepare,run_campaign
        if args.action=='report':
            from .campaign_report import write_campaign_report
            write_campaign_report(args.output); print(args.output/'report.html')
        elif args.action=='status':
            print((args.output/'state.json').read_text())
        else:
            config=load_config(args.config)
            result=prepare(config,args.output) if args.action=='prepare' else run_campaign(config,args.output)
            print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
