"""Evaluator-owned fitness and diverse parent selection. No LLM-assigned scores."""
import math
from pathlib import Path
import json

from .live_events import atomic_json


def assess_candidate(hypothesis,physics,novelty,reviews,config):
    crystal=hypothesis.crystal.structure()
    properties={
        'formula':crystal.composition.reduced_formula,'elements':sorted(e.symbol for e in crystal.composition.elements),
        'number_of_sites':len(crystal),'input_density_g_cm3':float(crystal.density),
        'input_volume_per_atom_angstrom3':float(crystal.volume/len(crystal)),
        'youngs_gpa':physics.get('youngs_gpa'),'shear_gpa':physics.get('shear_gpa'),
        'kappa_w_mk':physics.get('kappa_w_mk'),'epsilon_static':physics.get('epsilon_static'),
        'minimum_phonon_thz':physics.get('minimum_phonon_thz'),
        'energy_ev_per_atom':physics.get('artifacts',{}).get('energy_ev_per_atom'),
        'provenance':'Geometry from submitted structure; predicted properties only from evaluator output. No borrowed reference values.',
    }
    gates=[]
    def gate(name,value,condition,reason):
        status='unknown' if value is None else 'pass' if isinstance(value,(float,int,bool)) and math.isfinite(value) and condition(value) else 'fail'
        gates.append({'name':name,'value':value,'status':status,'reason':reason})
    gate('relaxation',physics.get('converged') if physics.get('backend')!='unconfigured' else None,bool,'Converged interatomic-potential relaxation')
    gate('dynamic_stability',physics.get('minimum_phonon_thz'),lambda v:v>=-1,'Minimum sampled phonon frequency >= -1 THz; finite-mesh screening only')
    if physics.get('minimum_phonon_thz') is not None and -1<=physics['minimum_phonon_thz']<-.1:
        gates[-1].update(status='unknown',reason='Small imaginary modes require displacement/supercell convergence checks; not credited as stable')
    gate('youngs_modulus',physics.get('youngs_gpa'),lambda v:v>=20,'Young modulus >= 20 GPa')
    gate('shear_modulus',physics.get('shear_gpa'),lambda v:v>=6,'Shear modulus >= 6 GPa')
    gate('thermal_conductivity',physics.get('kappa_w_mk'),lambda v:v>config.kappa_min_w_mk,'Minimum thermal tensor eigenvalue above configured threshold; preliminary until converged')
    gate('static_dielectric',physics.get('epsilon_static'),lambda v:1<=v<config.epsilon_static_max,'Static dielectric response in configured interval')
    known_match=bool(novelty.get('matches') or novelty.get('local_equivalent'))
    if known_match:gates.append({'name':'structural_novelty','status':'fail','value':None,'reason':'An equivalent known or previously proposed structure was found'})
    else:gates.append({'name':'structural_novelty','status':'unknown','value':None,'reason':'No match is not a proof of worldwide novelty'})
    gates.append({'name':'thermodynamic_stability','status':'unknown','value':None,'reason':'Complete same-model competing-phase hull not yet computed'})
    gates.append({'name':'synthesis_validation','status':'unknown','value':None,'reason':'Model route critique is not experimental validation'})
    tensor=physics.get('artifacts',{}).get('elastic_tensor_gpa')
    if tensor is not None:
        import numpy as np
        matrix=np.asarray(tensor,dtype=float)
        eigenvalue=float(np.linalg.eigvalsh((matrix+matrix.T)/2).min()) if matrix.shape==(6,6) and np.isfinite(matrix).all() else None
        properties['minimum_elastic_eigenvalue_gpa']=eigenvalue
        gate('mechanical_stability',eigenvalue,lambda v:v>0,'Positive definite stiffness under the evaluated zero-pressure convention; finite-strain numerical screening')
    failed=[g['name'] for g in gates if g['status']=='fail'];unknown=[g['name'] for g in gates if g['status']=='unknown']
    numerical_pass=sum(g['status']=='pass' for g in gates[:6])
    route_support=max((r.get('ranking_components',{}).get('supported_criteria',0)/6 for r in reviews),default=0)
    # Fitness improves measured target coverage. Unknowns cannot get success credit.
    vector=[numerical_pass/6,route_support,-len(failed)]
    return {'properties':properties,'gates':gates,'failed':failed,'unknown':unknown,
            'fitness':{'vector':vector,'dimensions':['predicted_physics_target_coverage','uncalibrated_route_support','negative_failed_checks'],
                       'selection_only':True,'not_a_success_probability':True},
            'selection_status':'rejected_for_current_objective' if failed else 'needs_more_tests',
            'validated_discovery':False,'test_level':'computational_screening_not_experimental_validation'}


def critic_prompt(hypothesis,assessment,novelty,reviews,evidence):
    return json.dumps({'task':'Act as a skeptical materials-science critic. Explain the current candidate\'s specific physical weaknesses and why changing composition or structure may address them. Do not invent properties, fabricate certainty, or override evaluator-owned numbers. Every finding must reference supplied evidence_fields or exact source citations. Separate measured/model-computed quantities from speculative mechanisms. Recommend a discriminating physical test and state tradeoffs.',
        'hypothesis':hypothesis.model_dump(),'assessment':assessment,'novelty':novelty,'route_reviews':reviews,
        'evidence':evidence,'allowed_evidence_fields':list(assessment['properties'])+[g['name'] for g in assessment['gates']]+['composition_audit.'+k for k in assessment.get('composition_audit',{})]})


def ground_critique(critique,assessment,store):
    allowed=set(assessment['properties'])|{g['name'] for g in assessment['gates']}|{'composition_audit.'+k for k in assessment.get('composition_audit',{})}
    result=critique.model_dump();findings=[]
    for original,finding in zip(critique.findings,result['findings']):
        checks=[store.validate_citation(c) for c in original.citations]
        fields=[f for f in finding['evidence_fields'] if f in allowed]
        findings.append({**finding,'valid_evidence_fields':fields,'citation_checks':checks,
                         'grounding':'traceable_inputs_not_verified_entailment' if fields or any(c['valid'] for c in checks) else 'unsupported_opinion'})
    result.update(findings=findings,calibrated=False,can_override_physics=False)
    return result


class Population:
    def __init__(self,path:Path,size=12):
        self.path=path;self.size=size
        self.entries=json.loads(path.read_text()).get('archive',[]) if path.exists() else []

    def add(self,dossier):
        if any(e['id']==dossier['id'] for e in self.entries):return
        assessment=dossier['assessment'];hypothesis=dossier['hypothesis']
        self.entries.append({'id':dossier['id'],'hypothesis':hypothesis,'crystal':dossier['evaluated_crystal'],
            'properties':assessment['properties'],'fitness':assessment['fitness']['vector'],
            'failed':assessment['failed'],'unknown':assessment['unknown'],'critic':dossier.get('critic'),
            'chemical_system':'-'.join(assessment['properties']['elements'])})
        atomic_json(self.path,{'archive':self.entries,'selected_parent_ids':[p['id'] for p in self.parents()],
                              'policy':'Pareto fronts then chemical-system diversity; retain all failures for critique',
                              'validated_discoveries':0})

    def parents(self):
        # Failed candidates remain visible as repair examples, but do not outrank feasible ones.
        pool=[e for e in self.entries if not e['failed']]
        if not pool:pool=self.entries[-self.size:]
        def dominates(a,b):return all(x>=y for x,y in zip(a['fitness'],b['fitness'])) and any(x>y for x,y in zip(a['fitness'],b['fitness']))
        ranked=sorted(pool,key=lambda a:(sum(dominates(b,a) for b in pool),len(a['failed']),-sum(a['fitness'][:2]),a['id']))
        selected=[];seen=set()
        for item in ranked:
            if item['chemical_system'] not in seen:
                selected.append(item);seen.add(item['chemical_system'])
                if len(selected)>=self.size:break
        for item in ranked:
            if len(selected)>=self.size:break
            if item not in selected:selected.append(item)
        return selected

    def context(self):
        def compact(entry):
            critique=entry.get('critic') or {}
            return {k:entry[k] for k in ['id','crystal','properties','fitness','failed','unknown']}|{
                'critique':{k:critique.get(k) for k in ['recommendation','why_try_a_different_material','suggested_changes','next_discriminating_test']}}
        return {'parents':[compact(e) for e in self.parents()[:4]],'recent_failures':[compact(e) for e in self.entries if e['failed']][-2:],
                'operators':['explore','substitute','recombine','distort','change_prototype','repair'],
                'instruction':'Select parent_ids only from this archive. Explain the physical problem addressed, the proposed mechanism and tradeoffs. Exploration without a parent is allowed. Do not repeat known equivalent structures.'}
