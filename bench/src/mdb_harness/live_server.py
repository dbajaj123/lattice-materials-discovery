"""Loopback-only dashboard and bounded subprocess campaign controller."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import tempfile
from urllib.parse import parse_qs, urlparse

from .campaign import load_config
from .discovery_schema import CampaignConfig
from .live_events import atomic_json, emit
from .research_client import credentials_ready

ASSETS=Path(__file__).parent/'web'
KEY_PROVIDERS={
    'openai':('OpenAI','OPENAI_API_KEY'),
    'anthropic':('Anthropic','ANTHROPIC_API_KEY'),
    'google':('Google','GOOGLE_API_KEY'),
    'openrouter':('OpenRouter','OPENROUTER_API_KEY'),
    'materials_project':('Materials Project (optional)','MP_API_KEY'),
}
SETTINGS_FIELDS={'model','review_model','rounds','candidates_per_round','routes_per_candidate',
                 'max_total_tokens','max_model_calls','thermal','thermal_max_displacements','simulation_timeout_seconds'}


def validate_settings(cfg,updates):
    if not isinstance(updates,dict) or set(updates)-SETTINGS_FIELDS:
        raise ValueError('Unsupported campaign settings')
    updates=dict(updates)
    for field in ['model','review_model']:
        if field not in updates:continue
        value=updates[field]
        if field=='review_model' and (value is None or value==''):
            updates[field]=None;continue
        if not isinstance(value,str) or not re.fullmatch(r'(openai|anthropic|google|openrouter)/[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}',value):
            raise ValueError('Use provider/model-id with openai, anthropic, google or openrouter')
        if any(part in ['','.','..'] for part in value.split('/')):
            raise ValueError('Model ID contains an invalid path segment')
    return CampaignConfig.model_validate({**cfg.model_dump(),**updates})


def read_json(path,default=None):
    try: return json.loads(path.read_text())
    except (OSError,ValueError): return default


def read_events(path):
    try: lines=path.read_text().splitlines()[-80:]
    except OSError: return []
    result=[]
    for line in lines:
        try: result.append(json.loads(line))
        except ValueError: pass
    return result


class Studio:
    def __init__(self,bench:Path):
        self.bench=bench.resolve()
        self.root=self.bench/'runs'
        self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.process=None
        self.active_id=None
        self.stopping=False
        self.csrf=secrets.token_urlsafe(32)
        self.session_keys=set()
        self._knowledge_cache=None

    def knowledge(self):
        if self._knowledge_cache and time.monotonic()-self._knowledge_cache[0]<60:return self._knowledge_cache[1]
        cfg=self.config();result={'materials':{'records':0},'literature':{'sources':0},'synthesis_paused':not cfg.synthesis_enabled}
        if cfg.reference_library and Path(cfg.reference_library).is_file():
            from .reference_library import ReferenceLibrary
            library=ReferenceLibrary(Path(cfg.reference_library))
            try:result['materials']=library.summary()
            finally:library.close()
        if cfg.literature_memory and Path(cfg.literature_memory).is_file():
            from .evidence import EvidenceStore
            memory=EvidenceStore(Path(cfg.literature_memory))
            try:result['literature']=memory.stats()
            finally:memory.close()
        self._knowledge_cache=(time.monotonic(),result)
        return result

    def search_knowledge(self,kind,query):
        cfg=self.config();query=query[:200]
        if kind=='materials':
            from .reference_library import ReferenceLibrary
            if not cfg.reference_library or not Path(cfg.reference_library).is_file():return []
            store=ReferenceLibrary(Path(cfg.reference_library))
            try:return store.search(query,limit=20)
            finally:store.close()
        from .evidence import EvidenceStore
        if not cfg.literature_memory or not Path(cfg.literature_memory).is_file():return {'sources':[],'research_notes':[]}
        store=EvidenceStore(Path(cfg.literature_memory))
        try:return {'sources':store.retrieve(query,limit=8,max_characters=16000),'research_notes':store.recall(query,limit=4)}
        finally:store.close()

    def catalog(self):
        result={}
        for name,kind,label in [('silicon-thermal','control','Silicon · reference calculation'),('discovery','discovery','Prepared discovery campaign')]:
            path=self.root/name
            if path.exists(): result[name]={'id':name,'kind':kind,'label':label,'path':path}
        for path in sorted((self.root/'live').glob('*/run.json'),reverse=True):
            meta=read_json(path,{})
            if meta.get('id')==path.parent.name:
                result[meta['id']]={**meta,'path':path.parent}
        return result

    def config(self):
        cfg=load_config(self.bench/'discovery.json')
        return validate_settings(cfg,read_json(self.root/'studio-settings.json',{}))

    def set_settings(self,payload):
        with self.lock:
            cfg=validate_settings(self.config(),payload)
            settings={k:getattr(cfg,k) for k in sorted(SETTINGS_FIELDS)}
            atomic_json(self.root/'studio-settings.json',settings)
            return {'settings':settings,'applies_to':'new_runs'}

    def key_options(self,cfg):
        providers=list(KEY_PROVIDERS)
        return [{'provider':provider,'label':KEY_PROVIDERS[provider][0],
                 'present':bool(os.environ.get(KEY_PROVIDERS[provider][1])),
                 'session_override':provider in self.session_keys}
                for provider in providers if provider in KEY_PROVIDERS]

    def set_api_key(self,payload):
        # This endpoint never calls a provider or includes the submitted value in errors/events.
        if set(payload)-{'provider','api_key','persist'}: raise ValueError('Unsupported credential fields')
        provider=payload.get('provider')
        if not isinstance(provider,str) or provider not in KEY_PROVIDERS: raise ValueError('Unsupported credential provider')
        value=payload.get('api_key'); persist=payload.get('persist',False)
        if not isinstance(value,str): raise ValueError('Enter an API key')
        value=value.strip()
        if not 8<=len(value)<=4096 or any(ord(c)<33 or ord(c)>126 for c in value) or '${' in value:
            raise ValueError('Enter a valid API key without spaces, line breaks or environment expressions')
        if type(persist) is not bool: raise ValueError('Local storage option must be true or false')
        environment_variable=KEY_PROVIDERS[provider][1]
        with self.lock:
            if persist:
                from dotenv import set_key
                destination=self.bench/'.env'
                if destination.is_symlink(): raise ValueError('Local .env must be a regular file to save credentials')
                descriptor,temporary=tempfile.mkstemp(prefix='.env.',suffix='.tmp',dir=self.bench)
                temp=Path(temporary)
                try:
                    with os.fdopen(descriptor,'w') as stream:
                        if destination.exists(): stream.write(destination.read_text())
                    set_key(temp,environment_variable,value,quote_mode='always')
                    temp.chmod(0o600)
                    temp.replace(destination)
                finally:
                    temp.unlink(missing_ok=True)
                self.session_keys.discard(provider)
            else:
                self.session_keys.add(provider)
            os.environ[environment_variable]=value
        return {'provider':provider,'present':True,'storage':'local_file' if persist else 'session',
                'validated':False,'applies_to':'new_runs'}

    def start(self,payload):
        mode=payload.get('mode','discovery')
        if mode not in ['discovery','control']: raise ValueError('Unknown run mode')
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError('A run is already active. Stop it before starting another.')
            cfg=self.config()
            updates=payload.get('settings',{})
            cfg=validate_settings(cfg,updates)
            if mode=='discovery':
                for model in [cfg.model,cfg.review_model or cfg.model]:
                    credential=credentials_ready(model)
                    if credential['present'] is False:
                        raise ValueError(f"Set {credential['environment_variable']} with the API key button to start discovery. The silicon control runs without a model key.")
            identifier=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)
            directory=self.root/'live'/identifier
            directory.mkdir(parents=True)
            label=('Discovery' if mode=='discovery' else 'Silicon control')+' · '+datetime.now().strftime('%H:%M')
            atomic_json(directory/'run.json',{'id':identifier,'kind':mode,'label':label,'created_at':datetime.now(timezone.utc).isoformat(),'status':'starting'})
            if mode=='discovery':
                atomic_json(directory/'launch-config.json',cfg.model_dump())
                command=[sys.executable,'-u','-m','mdb_harness.cli','discover','run','--config',str(directory/'launch-config.json'),'--output',str(directory),'--frozen-config']
            else:
                command=[sys.executable,'-u','-m','mdb_harness.cli','screen',str(self.bench/'examples/silicon-control.json'),
                         '--output',str(directory/'calculation'),'--backend','petmad','--elastic','--timeout',str(cfg.simulation_timeout_seconds)]
                if cfg.thermal: command+=['--thermal','--thermal-max-displacements',str(cfg.thermal_max_displacements)]
                atomic_json(directory/'config.json',cfg.model_dump())
            emit(directory,'starting','Starting a discovery campaign' if mode=='discovery' else 'Starting a real silicon control calculation')
            log=(directory/'process.log').open('w')
            try:
                self.process=subprocess.Popen(command,cwd=self.bench,env=dict(os.environ),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            except Exception:
                meta=read_json(directory/'run.json',{}); meta['status']='failed'; atomic_json(directory/'run.json',meta)
                raise
            finally: log.close()
            self.active_id=identifier; self.stopping=False
            threading.Thread(target=self._watch,args=(self.process,directory),daemon=True).start()
            return {'id':identifier,'status':'starting'}

    def _watch(self,process,directory):
        returncode=process.wait()
        with self.lock:
            meta=read_json(directory/'run.json',{})
            state=read_json(directory/'state.json',{})
            stopped=self.stopping and self.active_id==directory.name
            status='stopped' if stopped else state.get('status', 'complete' if returncode==0 else 'failed')
            if returncode and status not in ['stopped','budget_exhausted','failed']: status='failed'
            if meta.get('kind')=='control' and status=='complete':
                results=list((directory/'calculation/candidates').glob('*/evaluation.json'))
                physical=read_json(results[0],{}).get('physics',{}) if results else {}
                if not physical.get('converged'): status='failed'
            meta.update(status=status,returncode=returncode,finished_at=datetime.now(timezone.utc).isoformat())
            atomic_json(directory/'run.json',meta)
            if state and state.get('status')!=status:
                state['status']=status
                atomic_json(directory/'state.json',state)
            emit(directory,status,{'complete':'Run finished; results saved','stopped':'Run stopped; completed artifacts retained',
                                  'failed':'Run failed; inspect the saved progress and process.log'}.get(status,status.replace('_',' ')))
            if self.active_id==directory.name: self.stopping=False

    def stop(self):
        with self.lock:
            if self.process is None or self.process.poll() is not None: raise ValueError('No active run to stop')
            process=self.process; self.stopping=True
            os.killpg(process.pid,signal.SIGTERM)
            # Kill any remaining worker in this process group even if its parent exits first.
            def finish():
                time.sleep(3)
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            threading.Thread(target=finish,daemon=True).start()
            return {'status':'stopping','id':self.active_id}

    def _physics(self,folder):
        if folder is None: return {},None,[]
        evaluation=read_json(folder/'evaluation.json',{})
        physics=evaluation.get('physics') or read_json(folder/'physics.json') or read_json(folder/'physics-partial.json',{})
        return physics,read_json(folder/'live-structure.json'),read_events(folder/'progress.jsonl')

    def snapshot(self,selected=None):
        catalog=self.catalog()
        running=self.process is not None and self.process.poll() is None
        latest_complete=next((identifier for identifier,run in catalog.items() if run.get('status')=='complete'),None)
        fallback=self.active_id if running and self.active_id in catalog else latest_complete or next(iter(catalog),None)
        selected=selected if selected in catalog else fallback
        cfg=self.config()
        run=catalog.get(selected)
        candidates=[]; events=[]; sources=[]; calls=[]; state={}; status='idle'
        if run:
            root=run['path']; state=read_json(root/'state.json',{})
            status=run.get('status') or state.get('status') or ('complete' if run['kind']=='control' else 'prepared')
            events=read_events(root/'progress.jsonl')
            sources=read_json(root/'sources.json',[])
            calls=read_json(root/'model-calls/ledger.json',{}).get('calls',[])
            if run['kind']=='control':
                base=root/'calculation' if (root/'calculation').exists() else root
                for path in sorted((base/'candidates').glob('*/proposal.json')):
                    proposal=read_json(path,{})
                    physical,frame,activity=self._physics(path.parent); events+=activity
                    candidates.append({'id':path.parent.name,'hypothesis':proposal,'evaluated_crystal':physical.get('relaxed') or (frame or {}).get('crystal') or proposal.get('crystal'),
                        'physics':physical,'frame':frame,'routes':{'routes':[]},'route_assessments':[],
                        'kind':'known_control','novelty':{'structure_status':'known_material'},
                        'uncertainties':physical.get('warnings',[]),'complete':(path.parent/'evaluation.json').exists()})
            else:
                for folder in sorted((root/'candidates').glob('*')):
                    if not folder.is_dir(): continue
                    dossier=read_json(folder/'dossier.json',{})
                    hypothesis=dossier.get('hypothesis') or read_json(folder/'hypothesis.json')
                    if not hypothesis: continue
                    physics_folders=sorted((root/'physics').glob(folder.name+'*/candidates/*'))
                    physical,frame,activity=self._physics(physics_folders[-1] if physics_folders else None); events+=activity
                    candidates.append({**dossier,'id':folder.name,'hypothesis':hypothesis,
                        'evaluated_crystal':dossier.get('evaluated_crystal') or physical.get('relaxed') or (frame or {}).get('crystal') or hypothesis['crystal'],
                        'physics':dossier.get('physics') or physical,'frame':frame,
                        'routes':dossier.get('routes') or read_json(folder/'routes.json',{'routes':[]}),
                        'route_assessments':dossier.get('route_assessments') or read_json(folder/'live-assessments.json',[]),
                        'complete':bool(dossier)})
        # Current deterministic audit also makes legacy runs inspectable, without
        # rewriting their frozen records or inventing a retrospective LLM critique.
        from types import SimpleNamespace
        from .schema import Crystal
        from .chemistry import composition_audit,property_status
        from .evolution import assess_candidate
        from .capabilities import evaluator_capabilities
        run_config=read_json(run['path']/'config.json',{}) if run else {}
        audit_config=CampaignConfig.model_validate(run_config) if run_config else cfg
        for candidate in candidates:
            h=candidate['hypothesis'];subject=SimpleNamespace(name=h.get('name',''),crystal=Crystal.model_validate(h['crystal']))
            candidate['property_status']=property_status(candidate['physics'],run_config)
            candidate['composition_audit']=candidate.get('composition_audit') or composition_audit(subject)
            candidate['original_assessment']=candidate.get('assessment')
            candidate['assessment']=assess_candidate(subject,candidate['physics'],candidate.get('novelty',{}),candidate.get('route_assessments',[]),audit_config)
            candidate['assessment']['composition_audit']=candidate['composition_audit']
            candidate['assessment']['audit_origin']='Current deterministic audit of saved output; original run and critic are unchanged'
            if run and run['kind']!='control':
                folder=run['path']/'candidates'/candidate['id']
                candidate['critic']=candidate.get('critic') or read_json(folder/'critic.json')
            candidate['physics_warnings']=candidate['physics'].get('warnings',[])
        if running and selected==self.active_id: status='stopping' if self.stopping else 'running'
        elif run and run.get('status')=='starting': status='interrupted'
        events=sorted(events,key=lambda x:x.get('time',''))[-80:]
        used=sum(c.get('tokens_charged',c.get('tokens_reserved',0)) for c in calls)
        run_config=read_json(run['path']/'config.json',{}) if run else {}
        return {'selected_run':selected,'run':{k:v for k,v in (run or {}).items() if k!='path'},'status':status,
            'active_run':self.active_id if running else None,'running':running,
            'runs':[{k:v for k,v in r.items() if k!='path'} for r in reversed(list(catalog.values()))],
            'candidates':candidates,'events':events,'sources':sources,
            'model':run_config.get('model',cfg.model),
            'review_model':run_config.get('review_model') or run_config.get('model',cfg.model),
            'credentials':credentials_ready(run_config.get('model',cfg.model)),
            'review_credentials':credentials_ready(run_config.get('review_model') or run_config.get('model',cfg.model)),
            'key_options':self.key_options(cfg),
            'budget':{'calls':len(calls),'tokens':used,'max_tokens':run_config.get('max_total_tokens',cfg.max_total_tokens),
                'max_calls':run_config.get('max_model_calls',cfg.max_model_calls),
                'stop':read_json(run['path']/'model-calls/ledger.json',{}).get('budget_stop') if run else None},
            'knowledge':self.knowledge(),'capabilities':evaluator_capabilities(),'synthesis_paused':not cfg.synthesis_enabled,
            'population':read_json(run['path']/'population.json',{}) if run else {},
            'settings':{k:getattr(cfg,k) for k in sorted(SETTINGS_FIELDS)},
            'completed':len([c for c in candidates if c['complete']]),'state':state}


def make_server(studio,port=8768):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass

        def safe_host(self):
            return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']

        def send(self,status,payload,content_type='application/json'):
            body=json.dumps(payload,allow_nan=False).encode() if content_type=='application/json' else payload if isinstance(payload,bytes) else payload.encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Frame-Options','DENY')
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            if not self.safe_host(): return self.send(403,{'error':'Local host required'})
            url=urlparse(self.path); query=parse_qs(url.query); selected=query.get('run',[None])[0]
            if url.path=='/':
                return self.send(200,(ASSETS/'index.html').read_text().replace('__CSRF__',studio.csrf),'text/html; charset=utf-8')
            if url.path in ['/app.js','/style.css']:
                return self.send(200,(ASSETS/url.path[1:]).read_bytes(),'text/javascript' if url.path.endswith('.js') else 'text/css')
            if url.path=='/plotly.js':
                from plotly.offline import get_plotlyjs
                return self.send(200,get_plotlyjs(),'text/javascript')
            if url.path=='/api/state': return self.send(200,studio.snapshot(selected))
            if url.path in ['/api/library','/api/memory']:
                try:return self.send(200,studio.search_knowledge('materials' if url.path=='/api/library' else 'literature',query.get('q',[''])[0]))
                except (ValueError,OSError):return self.send(400,{'error':'Search unavailable for this query'})
            if url.path=='/api/events':
                self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.end_headers()
                previous=None
                try:
                    # Reconnect periodically; EventSource resumes by requesting a fresh complete snapshot.
                    for _ in range(120):
                        data=json.dumps(studio.snapshot(selected),allow_nan=False)
                        self.wfile.write(('data: '+data+'\n\n' if data!=previous else ': heartbeat\n\n').encode()); self.wfile.flush()
                        previous=data; time.sleep(1)
                except (BrokenPipeError,ConnectionResetError): pass
                return
            if url.path=='/api/cif':
                snapshot=studio.snapshot(selected)
                candidate=next((c for c in snapshot['candidates'] if c['id']==query.get('candidate',[''])[0]),None)
                if not candidate: return self.send(404,{'error':'Candidate not found'})
                from .schema import Crystal
                return self.send(200,Crystal.model_validate(candidate['evaluated_crystal']).structure().to(fmt='cif'),'chemical/x-cif')
            return self.send(404,{'error':'Not found'})

        def do_POST(self):
            origin=self.headers.get('Origin')
            if not self.safe_host() or self.headers.get('X-Studio-Token')!=studio.csrf or (origin and origin not in [f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}']):
                return self.send(403,{'error':'Local dashboard token required'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<0 or size>16384: return self.send(413,{'error':'Request too large'})
                payload=json.loads(self.rfile.read(size) or '{}')
                if not isinstance(payload,dict): raise ValueError('JSON object required')
                if self.path=='/api/start': return self.send(200,studio.start(payload))
                if self.path=='/api/stop': return self.send(200,studio.stop())
                if self.path=='/api/credentials': return self.send(200,studio.set_api_key(payload))
                if self.path=='/api/settings': return self.send(200,studio.set_settings(payload))
                return self.send(404,{'error':'Not found'})
            except ValueError as exc: return self.send(409,{'error':str(exc)[:600]})
            except Exception as exc: return self.send(500,{'error':f'Action failed ({type(exc).__name__})'})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser(description='Local live materials discovery studio')
    parser.add_argument('--bench',type=Path,default=Path.cwd())
    parser.add_argument('--port',type=int,default=8768)
    args=parser.parse_args()
    studio=Studio(args.bench)
    server=make_server(studio,args.port)
    print(f'Discovery studio: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if studio.process is not None and studio.process.poll() is None: studio.stop()
        server.server_close()


if __name__=='__main__': main()
