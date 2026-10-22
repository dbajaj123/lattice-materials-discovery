"""Streaming, versioned open-material snapshots with indexed structure lookup."""
from collections import Counter
from functools import reduce
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import zipfile
import zlib

from pymatgen.core import Composition, Structure, Element

from .evidence import now
from .novelty import StructureRegistry


def composition_key(species):
    counts=Counter(species)
    divisor=reduce(math.gcd,counts.values())
    return '|'.join(f'{element}:{count//divisor}' for element,count in sorted(counts.items()))


def structure_from_atoms(atoms):
    return Structure(atoms['lattice_mat'],atoms['elements'],atoms['coords'],coords_are_cartesian=atoms.get('cartesian',False))


def zip_records(path):
    with zipfile.ZipFile(path) as archive:
        names=[n for n in archive.namelist() if n.endswith('.json')]
        if len(names)!=1: raise ValueError('Expected one JSON data file in archive')
        with archive.open(names[0]) as stream:
            # Python's decoder accepts the NaN tokens present in upstream JARVIS.
            # Stream one record at a time; reject nonfinite geometry below.
            import codecs
            decoder=json.JSONDecoder();utf8=codecs.getincrementaldecoder('utf-8')()
            buffer='';started=False;ended=False;eof=False
            while not ended:
                if not eof:
                    chunk=stream.read(65536);eof=not chunk
                    buffer+=utf8.decode(chunk,final=eof)
                position=0
                while True:
                    while position<len(buffer) and buffer[position].isspace():position+=1
                    if not started:
                        if position>=len(buffer):break
                        if buffer[position]!='[':raise ValueError('Expected a JSON array')
                        started=True;position+=1;continue
                    while position<len(buffer) and (buffer[position].isspace() or buffer[position]==','):position+=1
                    if position>=len(buffer):break
                    if buffer[position]==']':ended=True;position+=1;break
                    try:row,end=decoder.raw_decode(buffer,position)
                    except json.JSONDecodeError:
                        if eof:raise
                        break
                    yield row;position=end
                buffer=buffer[position:]
                if eof and not ended:raise ValueError('Truncated JSON archive')
                if len(buffer)>16*1024*1024:raise ValueError('Oversized archive record')


PROPERTY_FIELDS={
    '_oqmd_band_gap','_oqmd_delta_e','_oqmd_stability','func','hse_gap','poisson','slme',
    'dfpt_piezo_max_dielectric','dfpt_piezo_max_dielectric_electronic','dfpt_piezo_max_dielectric_ionic',
    'formation_energy_peratom','formation_energy_per_atom','formation_energy','energy_per_atom',
    'optb88vdw_bandgap','mbj_bandgap','bandgap','band_gap','gap','bulk_modulus_kv','shear_modulus_gv',
    'elastic_tensor','epsx','epsy','epsz','mepsx','mepsy','mepsz','dfpt_piezo_max_dij',
    'dfpt_piezo_max_eij','dfpt_dielectric','dfpt_piezo','dfpt_dielectric_max','dfpt_dielectric_max_elec',
    'spg_number','spg_symbol','density','ehull','e_above_hull','stability','magmom_oszicar',
    'magmom_outcar','exfoliation_energy','Tc_supercon','nat','n_atoms','formula','reference',
}


class ReferenceLibrary:
    def __init__(self,path:Path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=60)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS datasets(name TEXT PRIMARY KEY,manifest TEXT NOT NULL,status TEXT NOT NULL,imported INTEGER DEFAULT 0,skipped INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS materials(dataset TEXT,material_id TEXT,formula TEXT,composition_key TEXT,chemsys TEXT,nsites INTEGER,properties TEXT,atoms BLOB,PRIMARY KEY(dataset,material_id));
        CREATE INDEX IF NOT EXISTS material_composition ON materials(composition_key);
        CREATE INDEX IF NOT EXISTS material_system ON materials(chemsys,nsites);
        CREATE INDEX IF NOT EXISTS material_formula ON materials(formula);
        ''')

    def import_archive(self,path:Path,*,dataset,manifest,progress=None):
        with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if manifest.get('computed_md5'):
            with path.open('rb') as stream: actual=hashlib.file_digest(stream,'md5').hexdigest()
            if actual!=manifest['computed_md5']: raise ValueError('Downloaded archive checksum differs from publisher manifest')
        prior=self.db.execute('SELECT * FROM datasets WHERE name=?',(dataset,)).fetchone()
        if prior and json.loads(prior['manifest'])['sha256']!=digest: raise ValueError('Dataset name already belongs to another archive; use a versioned name')
        if prior and prior['status']=='complete': return dict(prior)
        provenance={**manifest,'sha256':digest,'retrieved_at':now(),'scope':'finite published snapshot; not all existing materials'}
        self.db.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?,?,?)',(dataset,json.dumps(provenance),'importing',0,0));self.db.commit()
        imported=skipped=0;buffer=[]
        for index,row in enumerate(zip_records(path)):
            try:
                atoms=dict(row['atoms']); species=[s.strip() for s in atoms['elements']];atoms['elements']=species
                lattice=atoms['lattice_mat']; coords=atoms['coords']
                if not species or len(species)!=len(coords) or len(lattice)!=3: raise ValueError('Invalid structure shape')
                if any(not Element.is_valid_symbol(s) for s in set(species)): raise ValueError('Unresolved species')
                key=composition_key(species);chemsys='-'.join(sorted(set(species)))
                divisor=reduce(math.gcd,Counter(species).values())
                formula=''.join(e+(str(n//divisor) if n//divisor!=1 else '') for e,n in sorted(Counter(species).items()))
                identifier=str(row.get('jid') or row.get('id') or row.get('material_id') or row.get('_oqmd_entry_id') or row.get('oqmd_id') or index)
                properties={k:v for k,v in row.items() if k in PROPERTY_FIELDS and v not in [None,'na','None','']}
                # Missing property components do not invalidate otherwise usable geometry.
                def finite_values(value):
                    if isinstance(value,float) and not math.isfinite(value):return None
                    if isinstance(value,list):return [finite_values(v) for v in value]
                    if isinstance(value,dict):return {k:finite_values(v) for k,v in value.items()}
                    return value
                properties=finite_values(properties)
                record=(dataset,identifier,formula,key,chemsys,len(species),json.dumps(properties,allow_nan=False),
                        zlib.compress(json.dumps(atoms,separators=(',',':'),allow_nan=False).encode(),level=3))
                buffer.append(record);imported+=1
            except (KeyError,ValueError,TypeError): skipped+=1
            if len(buffer)>=2000:
                self._flush(buffer,dataset,imported,skipped);buffer=[]
                if progress: progress(imported,skipped)
        self._flush(buffer,dataset,imported,skipped)
        stored=self.db.execute('SELECT count(*) FROM materials WHERE dataset=?',(dataset,)).fetchone()[0]
        provenance.update(processed_records=imported+skipped,duplicate_ids=imported-stored)
        self.db.execute('UPDATE datasets SET status=?,imported=?,manifest=? WHERE name=?',('complete',stored,json.dumps(provenance),dataset));self.db.commit()
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return {'dataset':dataset,'imported':stored,'processed':imported+skipped,'skipped':skipped,'sha256':digest,'status':'complete'}

    def _flush(self,rows,dataset,imported,skipped):
        with self.db:
            self.db.executemany('INSERT OR REPLACE INTO materials VALUES(?,?,?,?,?,?,?,?)',rows)
            self.db.execute('UPDATE datasets SET imported=?,skipped=? WHERE name=?',(imported,skipped,dataset))

    def summary(self):
        datasets=[{**dict(row),'manifest':json.loads(row['manifest'])} for row in self.db.execute('SELECT * FROM datasets ORDER BY name')]
        return {'records':sum(d['imported'] for d in datasets),'datasets':datasets,'scope':'versioned open snapshots; incomplete global coverage'}

    def public_row(self,row,*,include_structure=False):
        result={k:row[k] for k in ['dataset','material_id','formula','chemsys','nsites']}
        result['reference_properties']=json.loads(row['properties'])
        result['property_provenance']='Imported reference calculations; not measurements or candidate predictions. Original property names and conventions retained.'
        if include_structure:
            from .schema import Crystal
            result['crystal']=Crystal.from_structure(structure_from_atoms(json.loads(zlib.decompress(row['atoms'])))).model_dump()
        return result

    def search(self,query='',limit=25):
        limit=min(max(int(limit),1),100)
        try:
            composition=Composition(query)
            integer,_=composition.get_integer_formula_and_factor()
            key=composition_key([str(e) for e,n in Composition(integer).items() for _ in range(int(n))])
            rows=self.db.execute('SELECT * FROM materials WHERE composition_key=? ORDER BY dataset,material_id LIMIT ?',(key,limit))
        except (ValueError,TypeError,KeyError):
            rows=self.db.execute('SELECT * FROM materials WHERE material_id LIKE ? OR formula=? ORDER BY dataset,material_id LIMIT ?',('%'+query[:80]+'%',query[:80],limit))
        return [self.public_row(row) for row in rows]

    def seed_candidates(self,elements,limit=12):
        from itertools import combinations
        systems=['-'.join(sorted(c)) for n in range(1,min(4,len(elements))+1) for c in combinations(elements,n)]
        selected=[]
        for system in systems:
            row=self.db.execute("SELECT * FROM materials WHERE chemsys=? AND nsites<=16 ORDER BY CASE WHEN dataset LIKE 'jarvis%' THEN 0 ELSE 1 END,nsites LIMIT 1",(system,)).fetchone()
            if row:
                try: selected.append(self.public_row(row,include_structure=True))
                except (ValueError,KeyError): pass
            if len(selected)>=limit: break
        return selected

    def match(self,crystal,max_checks=300):
        key=composition_key(crystal.species)
        total=self.db.execute('SELECT count(*) FROM materials WHERE composition_key=?',(key,)).fetchone()[0]
        rows=self.db.execute('SELECT * FROM materials WHERE composition_key=? ORDER BY dataset,material_id LIMIT ?',(key,max_checks)).fetchall()
        matcher=StructureRegistry().matcher;candidate=crystal.structure();matches=[];errors=0
        for row in rows:
            try:
                other=structure_from_atoms(json.loads(zlib.decompress(row['atoms'])))
                if matcher.fit(candidate,other): matches.append(self.public_row(row))
            except (ValueError,KeyError,TypeError): errors+=1
        return {'provider':'local_reference_library','status':'ok','matches':matches,
                'same_composition_records':total,'records_checked':len(rows),'comparison_errors':errors,
                'composition_lookup_complete':len(rows)==total and errors==0,
                'global_novelty_established':False,'datasets':[d['name'] for d in self.summary()['datasets']]}

    def close(self): self.db.close()
