"""Publish selected completed research records without keys, prompts or paper text."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime,timezone
from importlib.metadata import distribution
from pathlib import Path
import shutil

from plotly.offline import get_plotlyjs
from mdb_harness.campaign import code_hash
from mdb_harness.campaign_report import write_campaign_report
from mdb_harness.chemistry import composition_audit
from mdb_harness.discovery_schema import CandidateHypothesis


def export(bench,output):
    bench=bench.resolve();output=output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    def clean(value):
        if isinstance(value,dict):
            return {k:clean(v) for k,v in value.items() if k not in {'quote','api_key','authorization','headers','prompt','system'}}
        if isinstance(value,list):return [clean(v) for v in value]
        if isinstance(value,str):
            return value.replace(str(bench.parent),'[workspace]').replace(str(Path.home()),'[home]')
        return value
    def write(path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(clean(data),indent=2,allow_nan=False)+'\n')
    read=lambda p:json.loads(p.read_text())
    assets=output/'assets';assets.mkdir()
    bundle=get_plotlyjs();(assets/'plotly.min.js').write_text(bundle)
    dist=distribution('plotly')
    license_path=next(dist.locate_file(p) for p in dist.files if str(p).endswith('licenses/LICENSE.txt'))
    shutil.copy2(license_path,assets/'PLOTLY_LICENSE.txt')
    index=['# Published research reports — 2026-10-23','',
           'Completed computational runs, software validation and a historical audit. No experimentally validated material discovery is claimed. Synthesis was paused.',
           '', 'HTML reports contain interactive crystal viewers. Download this folder with its `assets/` directory and open a report locally; GitHub displays HTML source rather than running it.', '']
    for identifier in ['20261022-192943-b77799','20261022-201323-13ab62','20261022-212442-03b123']:
        source=bench/'runs/live'/identifier
        meta=read(source/'run.json');state=read(source/'state.json')
        if meta['status'] not in ['complete','budget_exhausted']:raise ValueError('Only finished runs may be published')
        dest=output/identifier;dest.mkdir()
        original_cfg=read(source/'config.json')
        config={k:v for k,v in original_cfg.items() if k not in ['reference_library','literature_memory','literature_files','seed_cif_files']}
        write(dest/'config.json',config);write(dest/'run.json',meta);write(dest/'state.json',state)
        write(dest/'manifest.json',read(source/'manifest.json'))
        sources=read(source/'sources.json')
        public_sources=[{k:s.get(k) for k in ['id','title','url','kind','sha256','retrieved_at']} for s in sources]
        write(dest/'sources.json',public_sources)
        ledger=read(source/'model-calls/ledger.json')
        write(dest/'usage.json',{'calls':[{k:c.get(k) for k in ['stage','model','status','started_at','finished_at','tokens_reserved','tokens_charged','usage']} for c in ledger['calls']],
                                  'budget_stop':ledger.get('budget_stop')})
        tokens=sum(c.get('tokens_charged',c.get('tokens_reserved',0)) for c in ledger['calls'])
        lines=[f'# Discovery run {identifier}','',f"Model: `{config['model']}`. Status: **{meta['status']}**. {len(ledger['calls'])} model requests; {tokens:,} charged/reserved tokens.",
               '', 'These are saved model predictions and original screening decisions, not verified discoveries. Missing properties are unassessed.', '',
               '| Candidate | Formula | Relaxation | Young (GPa) | Shear (GPa) | Thermal result |',
               '|---|---|---|---:|---:|---|']
        notes=[]
        for path in sorted((source/'candidates').glob('*/dossier.json')):
            raw=read(path);cdir=dest/'candidates'/raw['id'];cdir.mkdir(parents=True)
            fields=['id','kind','hypothesis','evaluated_crystal','hypothesis_citation_checks','physics','novelty',
                    'uncertainties','target_assessment','assessment','critic','composition_audit','synthesis_status',
                    'failed_physics','discovery_established','experimental_validation','official_comparable']
            dossier={k:raw.get(k) for k in fields}
            dossier.update(routes={'routes':[]},route_assessments=[],
                publication_notice='Saved model reasoning and checks are unverified. Citation excerpts and underlying paper text are omitted; consult sources.json for provenance.')
            current=composition_audit(CandidateHypothesis.model_validate(raw['hypothesis']))
            write(cdir/'current-composition-audit.json',current)
            old=raw.get('composition_audit',{}).get('label_discrepancies',[])
            if old and not current['label_discrepancies']:
                note=f"{raw['id']}: the original formula checker incorrectly treated an explicitly named parent prototype as the candidate formula. The checker is fixed in current code. This run's original preflight rejection is retained; physics was not rerun and no stability conclusion follows from that rejection."
                notes.append(note);dossier['publication_correction']=note
            write(cdir/'dossier.json',dossier)
            cif=path.parent/'candidate.cif'
            if cif.exists():shutil.copy2(cif,cdir/'candidate.cif')
            p=raw['physics'];transport=p.get('artifacts',{}).get('thermal',{})
            value=lambda key:'—' if p.get(key) is None else f'{p[key]:.2f}'
            thermal=value('kappa_w_mk')+' W/(m·K)' if p.get('kappa_w_mk') is not None else 'disabled' if not config.get('thermal') else transport.get('status','not calculated')
            if transport.get('required_displacements'):thermal+=f" ({transport['required_displacements']:,} displacements required)"
            relaxation='converged' if p.get('converged') else 'not converged' if p.get('relaxed') else 'not evaluated'
            lines.append(f"| {raw['id']} | {current['formula']} | {relaxation} | {value('youngs_gpa')} | {value('shear_gpa')} | {thermal} |")
        lines+=['','## Limits and corrections','',
                'Dielectric response, complete competing-phase hull and independent potential/DFT cross-checks were not calculated. Finite-mesh phonons and elastic predictions do not establish synthesis feasibility or global novelty.',
                '',f"Source coverage: {dict(Counter(s['kind'] for s in sources))}. Source metadata is included; abstracts, full papers and model request prompts are not redistributed.", '']
        lines+=['- '+note for note in notes]
        if identifier=='20261022-201323-13ab62':
            lines+=['','See [the detailed historical review](review.md) for density, acoustic-mode, citation and charge-balance issues. Original dossiers and critic findings are preserved as historical records.']
            (dest/'review.md').write_text(clean((source/'review.md').read_text()))
            write(dest/'current-audit.json',read(bench/'runs/report-fixes-20261023/audit.json'))
        lines+=['','[Interactive report](report.html) · [Source metadata](sources.json) · [Usage ledger](usage.json)','']
        (dest/'README.md').write_text('\n'.join(lines))
        write_campaign_report(dest)
        report=(dest/'report.html').read_text().replace('<script>'+bundle+'</script>','<script src="../assets/plotly.min.js"></script>')
        report=report.replace('<div class="muted">INDEPENDENT MATERIALS RESEARCH</div>',
            '<div class="muted">INDEPENDENT MATERIALS RESEARCH</div><p class="notice">Historical screening output. Read README.md for corrections and limitations. Unverified critic statements are preserved; citation excerpts are omitted.</p>')
        (dest/'report.html').write_text(report)
        index.append(f"- [{config['model']} · {identifier}](./{identifier}/README.md): {meta['status']}; {tokens:,} tokens.")
    controls=[]
    for identifier in ['20261022-211911-3eae5d','20261022-212006-237161','20261022-212211-d9fef6']:
        source=bench/'runs/live'/identifier
        result_path=next(source.glob('calculation/candidates/*/evaluation.json'))
        controls.append({'run':read(source/'run.json'),'configuration':read(source/'config.json'),
                         'calculation_manifest':read(source/'calculation/manifest.json'),
                         'evaluation':read(result_path)})
    # Strip machine-specific library paths from control configuration too.
    for row in controls:
        for key in ['reference_library','literature_memory','literature_files','seed_cif_files']:row['configuration'].pop(key,None)
    write(output/'silicon-controls.json',controls)
    write(output/'reference-recognition.json',read(bench/'runs/grounding-validation-confirmed/validation.json'))
    shutil.copy2(bench/'VALIDATION.md',output/'VALIDATION.md')
    index+=['','- [Software and simulator validation](VALIDATION.md)',
            '- [Silicon controls: full numerical outputs](silicon-controls.json)',
            '- [72/72 reference-recognition checks](reference-recognition.json)',
            '', 'The silicon transport value is a preliminary bulk RTA estimate, not a measurement or converged prediction. Recognition checks test known structures, not discovery success.',
            '', 'This export includes calculation settings, structures, numerical outputs, source metadata and original run source hashes. It excludes credentials, databases, model weights, model prompts, full paper text and large force-constant arrays. This is a report archive, not a standalone reproducible environment or a full raw-data deposit.',
            '', 'Plotly.js is shared by the HTML reports; its copyright header and [MIT license](assets/PLOTLY_LICENSE.txt) are retained.','']
    (output/'README.md').write_text('\n'.join(index))
    files={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}
    write(output/'export-manifest.json',{'exported_at':datetime.now(timezone.utc).isoformat(),
        'exporter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'current_package_sha256':code_hash(),'files_sha256':files,'original_runs_modified':False})
    print(f'Exported {len(files)+1} files to {output}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bench',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();export(args.bench,args.output)
