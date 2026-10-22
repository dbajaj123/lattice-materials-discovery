"""Scripted model integration test; no paid model calls or scientific claims."""
import hashlib
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root / 'runs').mkdir(exist_ok=True)
os.environ.setdefault('INSPECT_TRACE_FILE', str(root / 'runs' / 'inspect-trace.jsonl'))

from inspect_ai import eval
from inspect_ai.model import ChatMessageAssistant, ModelOutput, ModelUsage
from inspect_ai.tool import ToolCall
from mdb_harness.task import discovery
from mdb_harness.schema import Proposal

proposal = Proposal.model_validate_json((root / 'examples/silicon-control.json').read_text())
cid = hashlib.sha256(json.dumps(proposal.model_dump(), sort_keys=True).encode()).hexdigest()[:16]
sequence = [
    ('screen_candidate', {'proposal_json':proposal.model_dump_json()}),
    ('submit_candidate', {'candidate_id':cid}),
    ('submit', {'answer':'Control screened; no properties available in mock mode. Zero verified discoveries.'}),
]
outputs = []
for i,(name,arguments) in enumerate(sequence):
    output = ModelOutput.from_message(ChatMessageAssistant(content='',tool_calls=[ToolCall(id=str(i),function=name,arguments=arguments)]),stop_reason='tool_calls')
    output.usage = ModelUsage(input_tokens=100,output_tokens=100)
    outputs.append(output)
logs = eval(discovery(output=str(root/'runs/mock-agent'), backend='none',screen_budget=2,token_budget=2000),
            model='mockllm/model',model_args={'custom_outputs':outputs},log_dir=str(root/'runs/mock-logs'),display='none')
log = logs[0]
assert log.status == 'success', str(log.error)
assert log.samples and log.samples[0].scores
score = next(iter(log.samples[0].scores.values()))
assert score.value == 0, score
assert score.metadata['summary']['screen_calls'] == 1
assert score.metadata['summary']['submitted'] == [cid]
print(json.dumps({'status':log.status, 'scripted_model':True, 'tool_loop_verified':True,
                  'eligible_count':score.value, 'official_comparable':False}, indent=2))
