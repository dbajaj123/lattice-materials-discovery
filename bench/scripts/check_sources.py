"""Small live integration check; no LLM calls and no novelty claims."""
import json
from pathlib import Path
from ase.build import bulk
from pymatgen.io.ase import AseAtomsAdaptor
from mdb_harness.discovery_schema import CampaignConfig
from mdb_harness.evidence import EvidenceStore, collect_literature
from mdb_harness.material_data import MaterialData
from mdb_harness.schema import Crystal

root=Path(__file__).resolve().parents[1]/'runs/source-check'
root.mkdir(parents=True,exist_ok=True)
store=EvidenceStore(root/'evidence.sqlite')
literature=collect_literature(store,['aluminum nitride thin film deposition'],rows=3,max_open_papers=1)
sources=store.sources()
store.close()
config=CampaignConfig(database_max_pages=1,database_page_limit=3)
crystal=Crystal.from_structure(AseAtomsAdaptor.get_structure(bulk('Si','diamond',a=5.43)))
novelty=MaterialData(root/'database-cache',config).check_structure(crystal)
result={'sources':sources,'literature':literature,'known_silicon_control':novelty}
(root/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'source_kinds':[s['kind'] for s in sources],
                  'literature_queries':literature['coverage'],
                  'database_check':novelty},indent=2))
