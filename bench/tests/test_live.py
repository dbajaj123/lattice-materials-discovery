import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mdb_harness.discovery_schema import CampaignConfig
from mdb_harness.live_events import atomic_json,emit
from mdb_harness.live_server import Studio


@pytest.fixture
def studio(tmp_path):
    atomic_json(tmp_path/'discovery.json',CampaignConfig(network_enabled=False).model_dump())
    return Studio(tmp_path)


def test_live_snapshot_exposes_partial_structure_and_routes(studio):
    root=studio.root/'live'/'example'
    atomic_json(root/'run.json',{'id':'example','kind':'discovery','label':'Test run','status':'starting'})
    hypothesis={'name':'Fixture','hypothesis':'Test fixture only','crystal':{'lattice':[[4,0,0],[0,4,0],[0,0,4]],'species':['Si'],'frac_coords':[[0,0,0]]}}
    folder=root/'candidates/r00-c00'
    atomic_json(folder/'hypothesis.json',hypothesis)
    atomic_json(folder/'routes.json',{'routes':[{'name':'Unreviewed route','steps':[]}]})
    physical=root/'physics/r00-c00/candidates/abc'
    atomic_json(physical/'live-structure.json',{'step':2,'crystal':hypothesis['crystal']})
    emit(physical,'relaxation','Step two')
    snapshot=studio.snapshot('example')
    assert snapshot['status']=='interrupted'
    assert snapshot['candidates'][0]['frame']['step']==2
    assert snapshot['candidates'][0]['routes']['routes'][0]['name']=='Unreviewed route'
    assert not snapshot['candidates'][0]['complete']
    assert snapshot['events'][0]['message']=='Step two'


def test_live_rejects_unconfigured_model_before_launch(studio,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setattr(studio,'config',lambda:CampaignConfig())
    with pytest.raises(ValueError,match='Set OPENAI_API_KEY'):
        studio.start({'mode':'discovery'})
    assert not list((studio.root/'live').glob('*/run.json'))


def test_live_rejects_overlapping_runs_and_unapproved_settings(studio):
    studio.process=SimpleNamespace(poll=lambda:None)
    with pytest.raises(ValueError,match='already active'): studio.start({'mode':'control'})
    studio.process=None
    with pytest.raises(ValueError,match='Unsupported'): studio.start({'mode':'control','settings':{'command':'anything'}})


def test_stopped_run_is_not_reported_as_complete(studio):
    directory=studio.root/'live'/'cancelled'
    atomic_json(directory/'run.json',{'id':'cancelled','kind':'control','label':'Test'})
    studio.active_id='cancelled';studio.stopping=True
    studio._watch(SimpleNamespace(wait=lambda:-15),directory)
    assert studio.snapshot('cancelled')['status']=='stopped'


def test_failed_control_is_not_marked_complete(studio):
    directory=studio.root/'live'/'failed'
    atomic_json(directory/'run.json',{'id':'failed','kind':'control','label':'Test'})
    studio._watch(SimpleNamespace(wait=lambda:0),directory)
    assert studio.snapshot('failed')['status']=='failed'


def test_credentials_only_expose_presence(studio,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-secret-never-display')
    result=studio.snapshot()
    assert result['credentials']['present']
    assert 'test-secret-never-display' not in json.dumps(result)


def test_default_view_keeps_completed_result_after_stop(studio):
    for name,status in [('a-finished','complete'),('b-cancelled','stopped')]:
        atomic_json(studio.root/'live'/name/'run.json',{'id':name,'kind':'control','label':name,'status':status})
    studio.active_id='b-cancelled'
    assert studio.snapshot()['selected_run']=='a-finished'


def test_current_audit_uses_saved_run_settings_and_preserves_original(studio):
    root=studio.root/'live'/'historical'
    atomic_json(root/'run.json',{'id':'historical','kind':'discovery','label':'Fixture','status':'complete'})
    atomic_json(root/'config.json',CampaignConfig(thermal=False).model_dump())
    crystal={'lattice':[[4,0,0],[0,4,0],[0,0,4]],'species':['Si'],'frac_coords':[[0,0,0]]}
    original={'properties':{'input_density_g_cm3':123},'test_marker':'historical'}
    path=root/'candidates/r00-c00/dossier.json'
    atomic_json(path,{'hypothesis':{'name':'Fixture','crystal':crystal},'physics':{},'assessment':original})
    before=path.read_bytes()
    candidate=studio.snapshot('historical')['candidates'][0]
    assert candidate['property_status']['kappa_w_mk']=='disabled_by_configuration'
    assert candidate['original_assessment']==original
    assert candidate['assessment']['properties']['input_density_g_cm3']!=123
    assert path.read_bytes()==before


def test_api_key_session_storage_never_writes_or_returns_secret(studio,monkeypatch):
    import os
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    key='test-session-key-not-real'
    result=studio.set_api_key({'provider':'openai','api_key':key,'persist':False})
    assert os.environ['OPENAI_API_KEY']==key
    assert result['storage']=='session' and not result['validated']
    assert not (studio.bench/'.env').exists()
    assert key not in json.dumps(result)
    assert key not in json.dumps(studio.snapshot())


def test_saved_api_key_preserves_settings_and_has_private_permissions(studio,monkeypatch):
    import os
    import stat
    from dotenv import dotenv_values
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    destination=studio.bench/'.env'
    destination.write_text('# Keep this comment\nDISCOVERY_MODEL=openai/gpt-5.4\nOPENAI_API_KEY=old-test-key\n')
    key='new-persistent-test-key'
    result=studio.set_api_key({'provider':'openai','api_key':key,'persist':True})
    values=dotenv_values(destination)
    assert values['OPENAI_API_KEY']==key
    assert values['DISCOVERY_MODEL']=='openai/gpt-5.4'
    assert '# Keep this comment' in destination.read_text()
    assert stat.S_IMODE(destination.stat().st_mode)==0o600
    assert not list(studio.bench.glob('.env.*.tmp'))
    assert result['storage']=='local_file'
    assert key not in json.dumps(studio.snapshot())


def test_session_override_leaves_previously_saved_key_unchanged(studio,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    destination=studio.bench/'.env'
    original='OPENAI_API_KEY=previously-saved-test-key\n'
    destination.write_text(original)
    studio.set_api_key({'provider':'openai','api_key':'session-replacement-key'})
    assert destination.read_text()==original


@pytest.mark.parametrize('payload',[
    {'provider':'PATH','api_key':'secret-invalid-provider'},
    {'provider':'openai','api_key':'bad-key\nOTHER=secret'},
    {'provider':'openai','api_key':'bad-key-${OTHER}'},
    {'provider':'openai','api_key':'short'},
    {'provider':'openai','api_key':'otherwise-valid-key','persist':'true'},
])
def test_bad_key_input_rejected_without_echoing_value(studio,payload):
    with pytest.raises(ValueError) as error:
        studio.set_api_key(payload)
    assert payload['api_key'] not in str(error.value)
    assert not (studio.bench/'.env').exists()


def test_persistent_key_rejects_symlink_destination(studio,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    target=studio.bench/'other.env';target.write_text('UNCHANGED=yes\n')
    (studio.bench/'.env').symlink_to(target)
    with pytest.raises(ValueError,match='regular file'):
        studio.set_api_key({'provider':'openai','api_key':'do-not-write-test-key','persist':True})
    assert target.read_text()=='UNCHANGED=yes\n'


def test_model_settings_persist_and_override_environment(studio,monkeypatch):
    monkeypatch.setenv('DISCOVERY_MODEL','openai/environment-default')
    monkeypatch.setenv('DISCOVERY_REVIEW_MODEL','openai/environment-critic')
    result=studio.set_settings({'model':'anthropic/proposer-id','review_model':'openrouter/vendor/reviewer-id',
                               'thermal_max_displacements':500,'max_model_calls':30})
    reloaded=Studio(studio.bench)
    assert reloaded.config().model=='anthropic/proposer-id'
    assert reloaded.config().review_model=='openrouter/vendor/reviewer-id'
    assert result['settings']['thermal_max_displacements']==500
    reloaded.set_settings({'review_model':''})
    assert reloaded.config().review_model is None
    assert {r['provider'] for r in reloaded.key_options(reloaded.config())}=={'openai','anthropic','google','openrouter','materials_project'}


@pytest.mark.parametrize('payload',[{'model':'not-a-provider/model'},{'model':'openai/model with spaces'},
    {'model':42},{'model':'openai/../../secret'},{'thermal_max_displacements':0},{'command':'pwd'}])
def test_invalid_settings_leave_defaults_unchanged(studio,payload):
    with pytest.raises(ValueError):studio.set_settings(payload)
    assert not (studio.root/'studio-settings.json').exists()


def test_launched_config_keeps_selected_models(studio,monkeypatch):
    from mdb_harness.campaign import load_config
    captured={}
    monkeypatch.setenv('DISCOVERY_MODEL','openai/environment-default')
    monkeypatch.setenv('DISCOVERY_REVIEW_MODEL','openai/environment-critic')
    monkeypatch.setenv('OPENAI_API_KEY','test-not-a-real-key')
    def launch(command,**kwargs):
        captured['command']=command
        return SimpleNamespace(poll=lambda:None)
    monkeypatch.setattr('mdb_harness.live_server.subprocess.Popen',launch)
    monkeypatch.setattr('mdb_harness.live_server.threading.Thread',lambda **kwargs:SimpleNamespace(start=lambda:None))
    result=studio.start({'settings':{'model':'openai/selected-model','review_model':None}})
    assert '--frozen-config' in captured['command']
    cfg=load_config(studio.root/'live'/result['id']/'launch-config.json',environment_models=False)
    assert cfg.model=='openai/selected-model' and cfg.review_model is None


def test_stopping_updates_both_run_and_campaign_status(studio):
    directory=studio.root/'live'/'stopped'
    atomic_json(directory/'run.json',{'id':'stopped','kind':'discovery'})
    atomic_json(directory/'state.json',{'status':'running','completed_candidates':['r00-c00']})
    studio.active_id='stopped';studio.stopping=True
    studio._watch(SimpleNamespace(wait=lambda:-15),directory)
    assert json.loads((directory/'state.json').read_text())['status']=='stopped'
    assert json.loads((directory/'state.json').read_text())['completed_candidates']==['r00-c00']
