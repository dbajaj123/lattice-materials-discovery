"""Shared searchable paper corpus and clearly separated research memory."""
import hashlib
import json
from pathlib import Path
import re

from .evidence import EvidenceStore, now
from .reference_library import zip_records


def import_arxiv_archive(path:Path,database:Path,manifest,progress=None):
    with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    with path.open('rb') as stream: md5=hashlib.file_digest(stream,'md5').hexdigest()
    if manifest.get('computed_md5') and md5!=manifest['computed_md5']: raise ValueError('Literature archive checksum mismatch')
    store=EvidenceStore(database);name='arxiv-condmat-2023'
    prior=store.db.execute('SELECT * FROM imports WHERE name=?',(name,)).fetchone()
    if prior and json.loads(prior['manifest'])['sha256']!=digest:raise ValueError('Literature snapshot identity changed')
    if prior and prior['status']=='complete':
        result=store.stats();store.close();return result
    provenance={**manifest,'sha256':digest,'imported_at':now(),'kind':'abstract_archive','not_full_text':True}
    store.db.execute('INSERT OR REPLACE INTO imports VALUES(?,?,?,?)',(name,json.dumps(provenance),'importing',0));store.db.commit()
    store.batch_mode=True;count=skipped=0
    try:
        for row in zip_records(path):
            identifier=str(row.get('id',''));title=row.get('text','');abstract=row.get('ctext','')
            if not identifier or not abstract:skipped+=1;continue
            abstract=re.sub(r'^summarize:\s*','',abstract).replace('\\n',' ')
            store.add(title,'https://arxiv.org/abs/'+identifier,'abstract_archive',[('title and abstract',title+'\n'+abstract)])
            count+=1
            if count%2000==0:
                store.db.execute('UPDATE imports SET records=? WHERE name=?',(count,name));store.db.commit()
                if progress:progress(count,skipped)
        store.db.execute('UPDATE imports SET status=?,records=? WHERE name=?',('complete',count,name));store.db.commit()
        store.db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize')");store.db.commit()
        store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return {**store.stats(),'imported_records':count,'skipped':skipped,'sha256':digest}
    finally:store.close()


def retrieve_shared(local:EvidenceStore,path,query,limit=10,elements=None):
    if not path or not Path(path).exists():return []
    memory=EvidenceStore(Path(path))
    try:
        hits=memory.retrieve(query,limit=limit,elements=elements)
        local.import_sources(memory,[h['source_id'] for h in hits])
        local.query_log('shared_fts',query,'ok',{'source_ids':list(dict.fromkeys(h['source_id'] for h in hits)),
            'chemical_system':sorted(elements) if elements else None,'retrieval':'FTS5/BM25',
            'scope':'Bounded shared-memory retrieval; chemical mentions are not exact-phase evidence'})
        return [{**note,'text':note['text'][:2000],'context_excerpt':True} for note in memory.recall(query,limit=3)]
    finally:memory.close()


def commit_research_memory(path,root,store,dossier):
    if not path:return
    memory=EvidenceStore(Path(path))
    try:
        memory.import_sources(store,[s['id'] for s in store.sources()])
        assessment=dossier['assessment']
        text=json.dumps({'formula':assessment['properties']['formula'],'properties':assessment['properties'],
                         'failed_checks':assessment['failed'],'unknown_checks':assessment['unknown'],
                         'critic':dossier.get('critic'),'change_rationale':dossier['hypothesis'].get('change_rationale')})
        memory.remember(str(root),dossier['id'],'computational_result',text,[s['id'] for s in store.sources()])
    finally:memory.close()
