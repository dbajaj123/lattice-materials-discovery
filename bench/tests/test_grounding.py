import json
import zipfile
from pathlib import Path

import pytest
from ase.build import bulk
from pymatgen.io.ase import AseAtomsAdaptor

from mdb_harness.campaign import run_campaign
from mdb_harness.chemistry import composition_audit,property_status,hypothesis_preflight
from mdb_harness.discovery_schema import CampaignConfig,CandidateHypothesis,HypothesisBatch,HypothesisCritique,CriticFinding,Citation
from mdb_harness.evidence import EvidenceStore
from mdb_harness.evolution import assess_candidate,ground_critique
from mdb_harness.reference_library import ReferenceLibrary
from mdb_harness.schema import Crystal


def hypothesis():
    return CandidateHypothesis(name='Known silicon test fixture',hypothesis='Known silicon exercises orchestration, not discovery.',
        crystal=Crystal.from_structure(AseAtomsAdaptor.get_structure(bulk('Si','diamond',a=5.43))),
        expected_advantage='Control only',closest_known_material='silicon',falsification_test='Test known structure',
        change_rationale='Explicit test fixture for orchestration',predicted_mechanism='No new mechanism claimed')


def test_archive_nonfinite_properties_and_invalid_geometry(tmp_path):
    h=hypothesis();atoms={'elements':h.crystal.species,'lattice_mat':h.crystal.lattice,'coords':h.crystal.frac_coords,'cartesian':False}
    archive=tmp_path/'data.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('data.json',json.dumps([{'jid':'test-1','atoms':atoms,'epsx':float('nan')},
            {'jid':'bad','atoms':{**atoms,'coords':[[float('nan'),0,0],[.25,.25,.25]]}}]))
    library=ReferenceLibrary(tmp_path/'lib.sqlite')
    try:
        result=library.import_archive(archive,dataset='fixture',manifest={})
        assert result['imported']==1 and result['skipped']==1
        assert library.search('Si')[0]['reference_properties']['epsx'] is None
        assert library.match(h.crystal)['matches']
        assert library.summary()['records']==1
    finally:library.close()


def test_charge_and_formula_audit_rejects_false_balance_claim():
    h=hypothesis();h.name='BSiN3 derived network';h.crystal=Crystal(lattice=[[5,0,0],[0,5,0],[0,0,5]],
        species=['B','Si','N','N'],frac_coords=[[0,0,0],[.5,.5,0],[.5,0,.5],[0,.5,.5]])
    result=composition_audit(h)
    assert result['nominal_charge_per_cell']==1
    assert result['label_discrepancies'][0]['label_formula']=='BSiN3'
    assert result['charge_status']=='requires_bonding_justification'
    assert result['electronic_validation']=='not_computed'


def test_correct_formula_can_name_a_different_parent_prototype():
    h=hypothesis();h.name='BSiN2 — SiC-derived framework'
    h.crystal=Crystal(lattice=[[5,0,0],[0,5,0],[0,0,5]],species=['B','Si','N','N'],
        frac_coords=[[0,0,0],[.5,.5,0],[.5,0,.5],[0,.5,.5]])
    assert composition_audit(h)['label_discrepancies']==[]
    h.name='SiC-derived framework'
    assert composition_audit(h)['label_discrepancies']
    h.name='BSiN2 or BSiN3'
    assert composition_audit(h)['label_discrepancies'][0]['label_formula']=='BSiN3'


def test_physics_unknowns_instability_and_withheld_properties():
    h=hypothesis();cfg=CampaignConfig()
    empty=assess_candidate(h,{'backend':'unconfigured'}, {},[],cfg)
    assert empty['fitness']['vector'][0]==0 and not empty['validated_discovery']
    unstable=assess_candidate(h,{'converged':True,'minimum_phonon_thz':-17.89}, {},[],cfg)
    assert 'dynamic_stability' in unstable['failed']
    marginal=assess_candidate(h,{'minimum_phonon_thz':-.89}, {},[],cfg)
    assert 'dynamic_stability' in marginal['unknown']
    assert property_status({'artifacts':{'elastic_tensor_gpa':[]}})['youngs_gpa']=='withheld_invalid_or_unconverged'


def test_critic_is_untrusted_and_cannot_modify_physics(tmp_path):
    store=EvidenceStore(tmp_path/'e.sqlite');assessment=assess_candidate(hypothesis(),{}, {},[],CampaignConfig())
    before=json.dumps(assessment,sort_keys=True)
    critic=HypothesisCritique(recommendation='test_further',findings=[CriticFinding(domain='physics',severity='informational',
        issue='Unsupported favorable claim',evidence_fields=['fabricated_dielectric'],recommended_test='DFPT')],
        why_try_a_different_material='Test only',suggested_changes=[],tradeoffs=[],next_discriminating_test='DFPT')
    grounded=ground_critique(critic,assessment,store)
    assert grounded['findings'][0]['grounding']=='unsupported_opinion'
    assert not grounded['can_override_physics'] and not grounded['calibrated']
    assert json.dumps(assessment,sort_keys=True)==before;store.close()


def test_retrieval_filters_chemistry_and_preserves_citations(tmp_path):
    global_store=EvidenceStore(tmp_path/'global.sqlite');local=EvidenceStore(tmp_path/'local.sqlite')
    global_store.add('Unrelated','https://example.org/a','full_text_open_access',[('body','Platinum clusters exhibit phonon stability and high thermal conductivity.')])
    sid=global_store.add('Relevant chemical mentions','https://example.org/b','abstract_archive',[('abstract','Boron silicon nitride structures require tests of phonon stability.')])
    hits=global_store.retrieve('phonon stability',elements=['B','Si','N'])
    assert len(hits)==1 and hits[0]['source_id']==sid
    local.import_sources(global_store,[sid]);citation=Citation(source_id=sid,chunk_id=hits[0]['id'],quote='Boron silicon nitride structures')
    assert local.validate_citation(citation)=={'valid':True,'full_text':False,'reason':'Exact quote found; entailment still needs review'}
    global_store.remember('run','c1','computational_result','Boron silicon nitride test failed')
    assert 'not independent' in global_store.recall('boron')[0]['warning']
    assert len(global_store.retrieve('boron',max_characters=10))==0
    global_store.close();local.close()


class EvolutionFixture:
    def __init__(self):self.calls=[];self.prompts=[]
    def request(self,stage,prompt,schema,**kwargs):
        self.calls.append(stage);self.prompts.append(json.loads(prompt))
        if schema is HypothesisBatch:
            h=hypothesis()
            if stage=='propose:1':
                assert self.prompts[-1]['population']['parents'][0]['id']=='r00-c00'
                h.parent_ids=['r00-c00'];h.mutation_operator='repair';h.parent_issues_addressed=['Missing dielectric calculation']
            return HypothesisBatch(candidates=[h],reasoning_summary='Scripted test; not a discovered material')
        assert schema is HypothesisCritique,'Synthesis must stay paused'
        return HypothesisCritique(recommendation='repair',findings=[],why_try_a_different_material='Missing electronic response',
            suggested_changes=['Test a different bonding motif'],tradeoffs=['May reduce stiffness'],next_discriminating_test='Compute dielectric tensor')


def test_two_round_evolution_critic_memory_and_synthesis_pause(tmp_path):
    cfg=CampaignConfig(model='scripted/control',network_enabled=False,backend='none',rounds=2,candidates_per_round=1,
        literature_memory=str(tmp_path/'memory.sqlite'))
    client=EvolutionFixture();root=tmp_path/'run'
    state=run_campaign(cfg,root,client=client,skip_credential_check=True)
    assert state['status']=='complete'
    assert client.calls==['propose:0','critic:r00-c00','propose:1','critic:r01-c00']
    dossier=json.loads((root/'candidates/r01-c00/dossier.json').read_text())
    assert dossier['synthesis_status']=='paused_by_configuration'
    assert not dossier['routes']['routes'] and not dossier['discovery_established']
    assert dossier['hypothesis']['parent_ids']==['r00-c00']
    assert 'structural_novelty' in dossier['assessment']['failed']
    population=json.loads((root/'population.json').read_text());assert len(population['archive'])==2
    memory=EvidenceStore(Path(cfg.literature_memory));assert memory.stats()['research_notes']==2;memory.close()


def test_synthesis_cannot_run_after_instability(tmp_path,monkeypatch):
    monkeypatch.setattr('mdb_harness.campaign._evaluate',lambda *a:{'physics':{'backend':'fixture','converged':True,'minimum_phonon_thz':-17.89}})
    cfg=CampaignConfig(model='scripted/control',network_enabled=False,backend='none',rounds=1,candidates_per_round=1,synthesis_enabled=True)
    client=EvolutionFixture();root=tmp_path/'run';run_campaign(cfg,root,client=client,skip_credential_check=True)
    d=json.loads((root/'candidates/r00-c00/dossier.json').read_text());assert d['synthesis_status']=='blocked_by_physics'


def test_final_geometry_and_acoustic_minimum_do_not_reuse_input_density():
    h=hypothesis();final=h.crystal.model_copy(deep=True)
    final.lattice=[[v*.8 for v in row] for row in final.lattice]
    assessment=assess_candidate(h,{'converged':True,'relaxed':final.model_dump(),
        'minimum_phonon_thz':-3e-7},{},[],CampaignConfig())
    p=assessment['properties']
    assert p['final_density_g_cm3']==pytest.approx(p['input_density_g_cm3']/.8**3)
    assert p['final_geometry_converged']
    assert next(g for g in assessment['gates'] if g['name']=='dynamic_stability')['status']=='pass'


def test_bulk_and_poisson_are_derived_only_from_valid_isotropic_moduli():
    a=assess_candidate(hypothesis(),{'youngs_gpa':180.,'shear_gpa':75.},{},[],CampaignConfig())
    assert a['properties']['bulk_gpa']==pytest.approx(100.)
    assert a['properties']['poisson_ratio']==pytest.approx(.2)
    invalid=assess_candidate(hypothesis(),{'youngs_gpa':300.,'shear_gpa':75.},{},[],CampaignConfig())
    assert 'bulk_gpa' not in invalid['properties']


def test_property_status_distinguishes_disabled_budget_and_timeout():
    assert property_status({}, {'thermal':False})['kappa_w_mk']=='disabled_by_configuration'
    assert property_status({'artifacts':{'thermal':{'status':'budget_exceeded'}}})['kappa_w_mk']=='budget_exceeded'
    assert property_status({'artifacts':{'thermal':{'status':'timeout'}}})['kappa_w_mk']=='timeout'
    assert property_status({})['epsilon_static']=='backend_not_configured'


def test_citation_prefix_repair_does_not_repair_false_quotes(tmp_path):
    store=EvidenceStore(tmp_path/'e.sqlite')
    sid=store.add('Example','https://example.org/source','abstract',[('abstract','Silicon has a diamond structure.')])
    chunk=store.retrieve('silicon')[0]['id']
    c=Citation(source_id=sid,chunk_id=chunk.removeprefix(sid+':'),quote='Silicon has a diamond structure.')
    check=store.validate_citation(c)
    assert check['valid'] and check['identity_correction']['resolved_chunk_id']==chunk
    c.quote='Silicon has an invented structure.'
    critique=HypothesisCritique(recommendation='test_further',findings=[CriticFinding(domain='physics',severity='uncertain',
        issue='A fabricated quote with a real field',evidence_fields=['youngs_gpa'],citations=[c],recommended_test='Compute')],
        why_try_a_different_material='Fixture',suggested_changes=[],tradeoffs=[],next_discriminating_test='Compute')
    a=assess_candidate(hypothesis(),{}, {},[],CampaignConfig())
    assert ground_critique(critique,a,store)['findings'][0]['grounding']=='invalid_citation_requires_revision'
    store.close()


def test_unexplained_valence_repair_is_blocked_before_physics(tmp_path,monkeypatch):
    h=hypothesis();h.name='SiB2O4 candidate'
    h.crystal=Crystal(lattice=[[7,0,0],[0,7,0],[0,0,7]],species=['Si','B','B','O','O','O','O'],
        frac_coords=[[i/7,i/7,i/7] for i in range(7)])
    assert hypothesis_preflight(h)['status']=='requires_revision'
    def forbidden(*args):raise AssertionError('Inconsistent proposal must not consume a physics call')
    monkeypatch.setattr('mdb_harness.campaign._evaluate',forbidden)
    class Client:
        def request(self,*args,**kwargs):return HypothesisBatch(candidates=[h],reasoning_summary='Fixture')
    cfg=CampaignConfig(network_enabled=False,backend='none',rounds=1,candidates_per_round=1,critic_enabled=False)
    run_campaign(cfg,tmp_path/'run',client=Client(),skip_credential_check=True)
    d=json.loads((tmp_path/'run/candidates/r00-c00/dossier.json').read_text())
    assert 'proposal_consistency' in d['assessment']['failed']
    h.bonding_justification='Hypothesize mixed bonding; test the electronic occupations with DFT.'
    assert hypothesis_preflight(h)['status']=='ready_for_screening'
