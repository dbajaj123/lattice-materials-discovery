"""Preregister or execute matched-budget DEVELOPMENT runs, never an official SOTA claim."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--model',required=True,help='Inspect provider/model identifier')
parser.add_argument('--seeds',default='0,1,2,3,4')
parser.add_argument('--tokens',type=int,default=10000)
parser.add_argument('--screens',type=int,default=8)
parser.add_argument('--backend',choices=['none','petmad'],default='none')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--execute',action='store_true',help='Actually call the configured model provider; may incur cost')
args=parser.parse_args()
if args.tokens<=0 or args.screens<=0:
    parser.error('Budgets must be positive')
seeds=[int(x) for x in args.seeds.split(',')]
if len(seeds)!=len(set(seeds)):
    parser.error('Seeds must be distinct')
args.output.mkdir(parents=True,exist_ok=False)
plan={'created_at':datetime.now(timezone.utc).isoformat(),'model':args.model,'seeds':seeds,
      'strategies':['baseline','synthesis_first'],'tokens_per_run':args.tokens,'screen_calls_per_run':args.screens,
      'backend':args.backend,'maximum_total_tokens':2*len(seeds)*args.tokens,'official_comparable':False,
      'limitations':['Some providers do not support reproducible seeds; retain provider metadata.',
                     'Missing property models and the independent synthesis grader prevent discovery credit.',
                     'Published candidate structures and recipe verdicts are development data, not live search context.']}
(args.output/'plan.json').write_text(json.dumps(plan,indent=2))
if not args.execute:
    print(json.dumps({'plan':str(args.output/'plan.json'),'executed':False,'maximum_total_tokens':plan['maximum_total_tokens']}))
else:
    os.environ.setdefault('INSPECT_TRACE_FILE',str((args.output/'inspect-trace.jsonl').resolve()))
    from inspect_ai import eval
    from mdb_harness.task import discovery
    summaries=[]
    for seed in seeds:
        # Alternate order to reduce systematic time/provider-order confounding.
        strategies=plan['strategies'] if seed%2==0 else list(reversed(plan['strategies']))
        for strategy in strategies:
            logs=eval(discovery(strategy=strategy,output=str(args.output/f'seed-{seed}'),backend=args.backend,
                                screen_budget=args.screens,token_budget=args.tokens),
                      model=args.model,seed=seed,log_dir=str(args.output/'inspect-logs'))
            log=logs[0]
            summaries.append({'seed':seed,'strategy':strategy,'status':log.status,
                              'results':log.results.model_dump(mode='json') if log.results else None,
                              'official_comparable':False})
            (args.output/'results.json').write_text(json.dumps(summaries,indent=2))
            if log.status!='success':
                raise SystemExit('Run failed; stopped the campaign. Inspect logs before spending further budget.')
