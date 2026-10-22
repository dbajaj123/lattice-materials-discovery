import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from ase.build import bulk
from pymatgen.io.ase import AseAtomsAdaptor

from mdb_harness.campaign import prepare,run_campaign
from mdb_harness.discovery_schema import (CampaignConfig,CandidateHypothesis,Citation,HypothesisBatch,
    RouteStep,SynthesisRoute,RoutePortfolio,RouteAssessment,CriterionAssessment,StepAssessment,CRITERIA)
from mdb_harness.evidence import EvidenceStore
from mdb_harness.hull import reference_hull
from mdb_harness.material_data import MaterialData,optimade_structure
from mdb_harness.research_client import JSONResearchClient,BudgetExceeded
from mdb_harness.route_review import assess_route
from mdb_harness.schema import Crystal


def route(name='Route A',method='sputtering'):
    return SynthesisRoute(name=name,method=method,phase_selection_hypothesis='Unverified control hypothesis',
        steps=[RouteStep(operation='deposit test film',target_phase_or_state='silicon control',temperature_c=350)],
        expected_failure_modes=['Wrong phase'],required_equipment=['deposition tool'],unresolved_assumptions=['All mechanism evidence absent'])


def review(status='unknown',citations=None):
    return RouteAssessment(criteria=[CriterionAssessment(criterion=c,status=status,explanation='Test review',citations=citations or []) for c in CRITERIA],
                           critical_issues=[],next_experiment='Characterize the actual phase before property claims')


def test_citations_require_correct_source_and_exact_text(tmp_path):
    store=EvidenceStore(tmp_path/'e.sqlite')
    sid=store.add('Fixture paper','https://example.org/paper','full_text_local',[('methods','A documented deposition observation for this synthetic test.')])
    chunk=store.retrieve('deposition')[0]
    c=Citation(source_id=sid,chunk_id=chunk['id'],quote='A documented deposition observation')
    assert store.validate_citation(c)['valid']
    c.quote='A fabricated successful synthesis'
    assert not store.validate_citation(c)['valid']
    store.close()


def test_metadata_never_becomes_synthesis_support(tmp_path):
    store=EvidenceStore(tmp_path/'e.sqlite')
    sid=store.add('Deposition title','https://example.org','metadata',[('title','Deposition title of an unread paper')])
    chunk=store.retrieve('deposition')[0]
    c=Citation(source_id=sid,chunk_id=chunk['id'],quote='Deposition title of an unread paper')
    result=assess_route(route(),review('supported',[c]),store)
    assert all(x['status']=='unknown' for x in result['criteria'])
    assert result['synthesis_success_probability'] is None
    store.close()


def test_hard_temperature_conflict_overrides_model(tmp_path):
    store=EvidenceStore(tmp_path/'e.sqlite')
    r=route(); r.steps[0].temperature_c=600
    result=assess_route(r,review('supported'),store,max_wafer_c=400)
    assert result['status']=='reject_or_revise'
    assert next(x for x in result['criteria'] if x['criterion']=='thermal_budget')['status']=='contradicted'
    store.close()


def test_unsupported_step_judgment_is_downgraded(tmp_path):
    store=EvidenceStore(tmp_path/'e.sqlite')
    assessment=review()
    assessment.step_assessments=[StepAssessment(step=1,status='supported',explanation='Unsupported favorable assertion')]
    result=assess_route(route(),assessment,store)
    assert result['steps'][0]['status']=='unknown'
    assert result['steps'][0]['review']['explanation']=='Unsupported favorable assertion'
    store.close()


def test_hull_rejects_mixed_energy_models():
    e=lambda f,v,m='ml-a':{'formula':f,'total_energy_ev':v,'energy_model_sha256':m,'settings_sha256':'settings'}
    with pytest.raises(ValueError,match='never mix'):
        reference_hull(e('BN',-10),[e('B',-3),e('N',-4,'dft')])
    result=reference_hull(e('BN',-10),[e('B',-3),e('N',-4)])
    assert result['energy_above_supplied_hull_ev_atom']==0
    assert not result['global_thermodynamic_stability_established']


def test_failed_database_request_cannot_imply_novelty(tmp_path,monkeypatch):
    import requests
    def failure(*a,**k): raise requests.ConnectionError('test outage')
    monkeypatch.setattr(requests,'get',failure)
    cfg=CampaignConfig(optimade_endpoints={'test':'https://example.org/structures'})
    data=MaterialData(tmp_path,cfg)
    crystal=Crystal.from_structure(AseAtomsAdaptor.get_structure(bulk('Si','diamond',a=5.43)))
    result=data.check_structure(crystal)
    assert result['structure_status']=='unresolved'
    assert result['coverage'][0]['status']=='error'


def test_optimade_rejects_disorder():
    with pytest.raises(ValueError,match='Disordered'):
        optimade_structure({'attributes':{'species':[{'name':'site','chemical_symbols':['B','C'],'concentration':[.5,.5]}]}})


class ScriptedResearch:
    """Explicit known control fixture; no model intelligence or discoveries claimed."""
    def __init__(self): self.calls=0
    def request(self,stage,prompt,schema,**kwargs):
        self.calls+=1
        if schema is HypothesisBatch:
            crystal=Crystal.from_structure(AseAtomsAdaptor.get_structure(bulk('Si','diamond',a=5.43)))
            return HypothesisBatch(candidates=[CandidateHypothesis(name='Known silicon control',hypothesis='Known silicon tests orchestration only, not discovery.',
                crystal=crystal,expected_advantage='None; control only',closest_known_material='silicon',falsification_test='Compare against known silicon')],reasoning_summary='Scripted integration fixture')
        if schema is RoutePortfolio:
            return RoutePortfolio(routes=[route('Control route A','sputtering'),route('Control route B','CVD'),route('Control route C','transfer')])
        return review()


def test_entire_campaign_multiple_routes_and_resume(tmp_path,monkeypatch):
    # Explicit synthetic physics fixture to exercise the optional route renderer.
    monkeypatch.setattr('mdb_harness.campaign._evaluate',lambda *args:{'physics':{'backend':'test_fixture','converged':True,'minimum_phonon_thz':0},'gates':[]})
    cfg=CampaignConfig(name='Scripted silicon integration test',model='scripted/control',network_enabled=False,backend='none',rounds=1,candidates_per_round=1,synthesis_enabled=True,critic_enabled=False)
    client=ScriptedResearch()
    result=run_campaign(cfg,tmp_path/'campaign',client=client,skip_credential_check=True)
    assert result['status']=='complete' and len(result['completed_candidates'])==1
    assert client.calls==5
    dossier=json.loads((tmp_path/'campaign/candidates/r00-c00/dossier.json').read_text())
    assert len(dossier['routes']['routes'])==3
    assert all(r['status']=='insufficient_evidence' for r in dossier['route_assessments'])
    assert not dossier['discovery_established']
    assert dossier['novelty']['structure_status']=='unresolved'
    assert (tmp_path/'campaign/candidates/r00-c00/candidate.cif').exists()
    assert (tmp_path/'campaign/report.html').exists()
    run_campaign(cfg,tmp_path/'campaign',client=client,skip_credential_check=True)
    assert client.calls==5


def test_prepare_and_run_wait_for_key_without_model_calls(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    cfg=CampaignConfig(network_enabled=False)
    state=run_campaign(cfg,tmp_path/'prepared')
    assert state['status']=='awaiting_model_credentials'
    assert not (tmp_path/'prepared/model-calls').exists()
    assert 'awaiting_model_credentials' in (tmp_path/'prepared/report.html').read_text()


def test_model_budget_stops_before_provider_call(tmp_path,monkeypatch):
    from inspect_ai import model
    monkeypatch.setattr(model,'get_model',lambda *a,**k: pytest.fail('Provider must not be reached'))
    cfg=CampaignConfig(max_total_tokens=1000)
    client=JSONResearchClient(tmp_path,cfg)
    with pytest.raises(BudgetExceeded): client.request('test','prompt',RouteAssessment)


def test_json_client_validates_caches_and_records_usage(tmp_path,monkeypatch):
    from inspect_ai import model
    from inspect_ai.model import ModelOutput,ModelUsage
    calls=[]
    class Provider:
        async def generate(self,messages):
            calls.append(messages)
            result=ModelOutput.from_content(model='mock',content=review().model_dump_json())
            result.usage=ModelUsage(input_tokens=100,output_tokens=100)
            return result
    monkeypatch.setattr(model,'get_model',lambda *a,**k:Provider())
    client=JSONResearchClient(tmp_path,CampaignConfig())
    assert client.request('review','prompt',RouteAssessment)==review()
    assert client.request('review','prompt',RouteAssessment)==review()
    assert len(calls)==1
    assert client.ledger['calls'][0]['tokens_charged']==200


def test_lookup_retries_expired_failures_without_refetching_success(tmp_path,monkeypatch):
    from mdb_harness.evidence import now
    cfg=CampaignConfig(optimade_endpoints={'oqmd':'https://example.org'})
    data=MaterialData(tmp_path,cfg);calls={'oqmd':0,'mp':0}
    def oqmd(*args):
        calls['oqmd']+=1
        return {'provider':'oqmd','retrieved_at':'2000-01-01T00:00:00+00:00' if calls['oqmd']==1 else now(),
                'status':'error' if calls['oqmd']==1 else 'ok','records':[],'complete':False}
    def mp(*args):
        calls['mp']+=1
        return {'provider':'materials_project','retrieved_at':now(),'status':'ok','records':[],'complete':True}
    monkeypatch.setattr(data,'_fetch_optimade',oqmd);monkeypatch.setattr(data,'_fetch_mp',mp)
    assert data.lookup(['Si'])['providers'][0]['status']=='error'
    assert data.lookup(['Si'])['providers'][0]['status']=='ok'
    assert calls=={'oqmd':2,'mp':1}


def test_selected_review_model_reaches_provider(tmp_path,monkeypatch):
    from inspect_ai import model
    from inspect_ai.model import ModelOutput,ModelUsage
    seen=[]
    class Provider:
        async def generate(self,messages):
            result=ModelOutput.from_content(model='mock',content=review().model_dump_json())
            result.usage=ModelUsage(input_tokens=100,output_tokens=100)
            return result
    def get(name,**kwargs):seen.append(name);return Provider()
    monkeypatch.setattr(model,'get_model',get)
    client=JSONResearchClient(tmp_path,CampaignConfig(model='openai/chosen',review_model='anthropic/critic'))
    client.request('propose','prompt',RouteAssessment)
    client.request('critic','prompt',RouteAssessment,review=True)
    assert seen==['openai/chosen','anthropic/critic']
