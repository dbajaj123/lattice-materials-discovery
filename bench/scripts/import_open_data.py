"""Stream the downloaded, publisher-checksummed snapshots into compact indexes."""
import argparse
import json
from pathlib import Path

from mdb_harness.reference_library import ReferenceLibrary
from mdb_harness.literature_memory import import_arxiv_archive

parser=argparse.ArgumentParser()
parser.add_argument('--kind',choices=['materials','literature'],required=True)
parser.add_argument('--download',action='store_true',help='Download missing versioned public archives before importing')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'open-snapshots.json').read_text())
if args.download:
    import requests
    names=['jarvis-2025','oqmd-2021'] if args.kind=='materials' else ['arxiv-condmat-2023']
    for name in names:
        source=catalog[name];destination=root/source['archive']
        if destination.exists():continue
        destination.parent.mkdir(parents=True,exist_ok=True)
        partial=destination.with_suffix('.partial')
        with requests.get(source['download_url'],stream=True,timeout=60) as response:
            response.raise_for_status()
            with partial.open('wb') as handle:
                for chunk in response.iter_content(1024*1024):handle.write(chunk)
        import hashlib
        with partial.open('rb') as handle:checksum=hashlib.file_digest(handle,'md5').hexdigest()
        if checksum!=source['computed_md5']:raise ValueError('Publisher checksum verification failed')
        partial.replace(destination)
if args.kind=='materials':
    library=ReferenceLibrary(root/'data/reference/materials.sqlite')
    try:
        for name in ['jarvis-2025','oqmd-2021']:
            source=catalog[name]
            result=library.import_archive(root/source['archive'],dataset=name,manifest=source,
                progress=lambda n,s:print(json.dumps({'dataset':name,'imported':n,'skipped':s}),flush=True))
            print(json.dumps(result),flush=True)
        (root/'data/reference/summary.json').write_text(json.dumps(library.summary(),indent=2))
    finally:library.close()
else:
    source=catalog['arxiv-condmat-2023']
    result=import_arxiv_archive(root/source['archive'],root/'data/literature/memory.sqlite',source,
        progress=lambda n,s:print(json.dumps({'abstracts':n,'skipped':s}),flush=True))
    (root/'data/literature/summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
