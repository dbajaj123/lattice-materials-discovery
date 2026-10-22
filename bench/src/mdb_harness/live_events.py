"""Small persisted progress events shared by the runner and live dashboard."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False))
    temporary.replace(path)


def emit(root: Path,stage: str,message: str,**details):
    root.mkdir(parents=True,exist_ok=True)
    event={'time':datetime.now(timezone.utc).isoformat(),'stage':stage,'message':message,**details}
    with (root/'progress.jsonl').open('a') as stream:
        stream.write(json.dumps(event,allow_nan=False)+'\n')
    atomic_json(root/'progress.json',event)
    return event
