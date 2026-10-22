"""Reproducible reference-recognition tests and optional real simulator controls."""
import json
from pathlib import Path

from .engine import Engine, dump
from .reference_library import ReferenceLibrary, structure_from_atoms
from .schema import Crystal


def validate(library_path,output,simulate=False,cases=12):
    import zlib
    library=ReferenceLibrary(Path(library_path));tests=[]
    try:
        summary=library.summary()
        for dataset in summary['datasets']:
            rows=library.db.execute('SELECT * FROM materials WHERE dataset=? AND nsites<=8 ORDER BY material_id LIMIT ?',
                                    (dataset['name'],cases)).fetchall()
            for row in rows:
                structure=structure_from_atoms(json.loads(zlib.decompress(row['atoms'])))
                for representation in ['original','translated','supercell']:
                    changed=structure.copy()
                    if representation=='translated':changed.translate_sites(range(len(changed)),[.173,.281,.391],frac_coords=True,to_unit_cell=True)
                    if representation=='supercell':changed.make_supercell([2,1,1])
                    try:
                        match=library.match(Crystal.from_structure(changed))
                        tests.append({'dataset':row['dataset'],'id':row['material_id'],'representation':representation,
                                      'known_match_recovered':bool(match['matches']),'checked':match['records_checked'],
                                      'lookup_complete':match['composition_lookup_complete']})
                    except (ValueError,TypeError) as exc:
                        tests.append({'dataset':row['dataset'],'id':row['material_id'],'representation':representation,
                                      'known_match_recovered':False,'error':type(exc).__name__})
    finally:library.close()
    report={'scope':'Known-reference recognition under equivalent structure representations; not blind discovery or synthesis success.',
            'library_records':summary['records'],'tests':tests,'passed':sum(t['known_match_recovered'] for t in tests),
            'total':len(tests),'simulator_controls':[],'experimental_validation':False,'sota_comparison':False}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    dump(output/'validation.json',report)
    if simulate:
        from ase.build import bulk
        from pymatgen.io.ase import AseAtomsAdaptor
        engine=Engine(output/'controls',backend='petmad',elastic=True,timeout=300,max_screen_calls=3)
        for name,a in [('Si',5.43),('C',3.57)]:
            crystal=Crystal.from_structure(AseAtomsAdaptor.get_structure(bulk(name,'diamond',a=a)))
            result=engine.screen({'name':name+' known diamond control','hypothesis':'Known structure used only to check the numerical screening pipeline.','crystal':crystal.model_dump()})
            physics=result.get('physics',{})
            report['simulator_controls'].append({'name':name,'physics':physics,'gates':result.get('gates'),
                'computed_moduli':physics.get('youngs_gpa') is not None and physics.get('shear_gpa') is not None,
                'interpretation':'Simulator smoke test; does not measure accuracy against DFT or experiment.'})
            dump(output/'validation.json',report)
    return report
