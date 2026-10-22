"""Cached structure lookups. Coverage and provider failures remain explicit."""
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urljoin, urlparse

from pymatgen.core import Structure
import requests

from .evidence import now
from .novelty import StructureRegistry


def optimade_structure(record):
    attrs=record['attributes']
    if attrs.get('dimension_types',[1,1,1]) != [1,1,1]:
        raise ValueError('Only 3D periodic structures are currently screened')
    mapping={}
    for species in attrs['species']:
        symbols=species['chemical_symbols']
        concentrations=species.get('concentration',[1.0])
        if len(symbols)!=1 or concentrations != [1.0] or symbols[0] in ['X','vacancy']:
            raise ValueError('Disordered or vacant sites require an explicit ordered model')
        mapping[species['name']]=symbols[0]
    return Structure(attrs['lattice_vectors'],[mapping[s] for s in attrs['species_at_sites']],
                     attrs['cartesian_site_positions'],coords_are_cartesian=True)


class MaterialData:
    def __init__(self,cache:Path,config):
        self.cache=cache; self.config=config
        cache.mkdir(parents=True,exist_ok=True)

    def _fetch_optimade(self,name,endpoint,elements):
        result={'provider':name,'endpoint':endpoint,'retrieved_at':now(),'records':[],
                'complete':False,'skipped_records':0,'status':'unknown'}
        filters='elements HAS ALL '+','.join(json.dumps(x) for x in elements)+f' AND nelements={len(elements)}'
        if name=='jarvis':
            # This provider has returned site counts in nelements; filter exact chemistry locally.
            filters='elements HAS ALL '+','.join(json.dumps(x) for x in elements)
        url=endpoint
        params={'filter':filters,'page_limit':self.config.database_page_limit}
        try:
            for _ in range(self.config.database_max_pages):
                response=requests.get(url,params=params,timeout=20)
                response.raise_for_status()
                data=response.json()
                if 'data' not in data:
                    raise ValueError('No OPTIMADE data array')
                for row in data['data']:
                    try:
                        s=optimade_structure(row)
                        if sorted(e.symbol for e in s.composition.elements)!=elements:
                            continue
                        result['records'].append({'id':row['id'],'structure':s.as_dict()})
                    except (ValueError,KeyError,TypeError):
                        result['skipped_records']+=1
                link=data.get('links',{}).get('next')
                if isinstance(link,dict): link=link.get('href')
                if not link:
                    result['complete']=not data.get('meta',{}).get('more_data_available',False) and result['skipped_records']==0
                    break
                next_url=urljoin(url,link)
                if urlparse(next_url).netloc!=urlparse(endpoint).netloc:
                    raise ValueError('Pagination changed provider host')
                if endpoint.startswith('https://') and next_url.startswith('http://'):
                    next_url='https://'+next_url[len('http://'):]
                url,params=next_url,None
            result['status']='ok' if result['records'] else 'empty_unverified'
            if not result['records']:
                result['complete']=False  # Empty service responses are not a novelty certificate.
        except (requests.RequestException,ValueError,KeyError) as exc:
            result.update(status='error',error_type=type(exc).__name__,complete=False)
        return result

    def _fetch_mp(self,elements):
        result={'provider':'materials_project','retrieved_at':now(),'records':[],'complete':False}
        key=os.environ.get('MP_API_KEY') or os.environ.get('MATERIALS_PROJECT_API_KEY')
        if not key:
            return {**result,'status':'missing_optional_key'}
        try:
            for page in range(self.config.database_max_pages):
                response=requests.get('https://api.materialsproject.org/materials/summary/',headers={'X-API-KEY':key},
                    params={'chemsys':'-'.join(elements),'_fields':'material_id,structure,formula_pretty',
                            '_limit':self.config.database_page_limit,'_skip':page*self.config.database_page_limit},timeout=25)
                response.raise_for_status()
                payload=response.json(); rows=payload['data']
                result['records'].extend({'id':row['material_id'],'structure':row['structure']} for row in rows)
                if len(result['records'])>=payload.get('meta',{}).get('total_doc',float('inf')) or len(rows)<self.config.database_page_limit:
                    result['complete']=True; break
            result['status']='ok'
        except (requests.RequestException,ValueError,KeyError) as exc:
            result.update(status='error',error_type=type(exc).__name__,complete=False)
        return result

    def lookup(self,elements):
        elements=sorted(set(elements))
        identity={'elements':elements,'endpoints':self.config.optimade_endpoints,
                  'page_limit':self.config.database_page_limit,'pages':self.config.database_max_pages,
                  'mp_key_present':bool(os.environ.get('MP_API_KEY') or os.environ.get('MATERIALS_PROJECT_API_KEY'))}
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
        file=self.cache/f'{digest}.json'
        if file.exists(): return json.loads(file.read_text())
        shared=Path(self.config.reference_library).parent/'api-cache'/file.name if self.config.reference_library else None
        if shared and shared.exists() and time.time()-shared.stat().st_mtime<7*86400:
            result=json.loads(shared.read_text());file.write_text(json.dumps(result,indent=2));return result
        if not self.config.network_enabled:
            return {'chemical_system':'-'.join(elements),'providers':[],'status':'network_disabled'}
        providers=[self._fetch_optimade(name,url,elements) for name,url in self.config.optimade_endpoints.items()]
        providers.append(self._fetch_mp(elements))
        result={'chemical_system':'-'.join(elements),'providers':providers,'status':'queried'}
        file.write_text(json.dumps(result,indent=2))
        if shared and any(p['records'] for p in providers):
            from .engine import dump
            dump(shared,result)
        return result

    def check_structure(self,crystal):
        matches=[]; matcher=StructureRegistry().matcher
        local=None
        if self.config.reference_library and Path(self.config.reference_library).is_file():
            from .reference_library import ReferenceLibrary
            library=ReferenceLibrary(Path(self.config.reference_library))
            try:local=library.match(crystal)
            finally:library.close()
            matches.extend({'provider':r['dataset'],'id':r['material_id'],'reference_properties':r['reference_properties']} for r in local['matches'])
        data={'providers':[]} if matches else self.lookup(crystal.species)
        for provider in data['providers']:
            for row in provider['records']:
                try:
                    if matcher.fit(crystal.structure(),Structure.from_dict(row['structure'])):
                        matches.append({'provider':provider['provider'],'id':row['id']})
                except (ValueError,KeyError,TypeError):
                    continue
        return {'structure_status':'known_structure_match' if matches else 'unresolved', 'matches':matches,
                'coverage':[{k:v for k,v in p.items() if k!='records'}|{'records_checked':len(p['records'])} for p in data['providers']],
                'local_library':local,'online_lookup':'skipped_known_local_match' if local and local['matches'] else data.get('status'),
                'literature_novelty':'unresolved','scope':'Chemical-system structure search; thin-film/process novelty needs separate review'}
