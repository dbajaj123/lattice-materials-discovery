"""Real browser + live control integration; no model API calls."""
import copy
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
base='http://127.0.0.1:8768'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1200},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base,wait_until='load')
    page.wait_for_function("document.querySelector('#crystal').data?.length > 0",timeout=60000)
    assert page.locator('#material-kind').inner_text()=='KNOWN CONTROL'
    initial=page.request.get(base+'/api/state').json()
    assert page.request.post(base+'/api/start',data={'mode':'control'}).status==403
    if initial['credentials']['present'] is False:
        page.locator('#start-button').click()
        page.wait_for_function("document.querySelector('#notice').textContent.includes('Set OPENAI_API_KEY')")
    page.locator('#settings-button').click()
    page.locator('input[name=thermal]').check()
    page.locator('#settings-form button[type=submit]').click()
    page.locator('#control-button').click()
    page.wait_for_function("document.querySelector('#status').textContent === 'running'",timeout=30000)
    page.wait_for_function("document.querySelector('#crystal').data?.length > 0",timeout=90000)
    page.screenshot(path=str(root/'runs/studio-running.png'),full_page=True)
    page.wait_for_function("document.querySelector('#status').textContent === 'complete'",timeout=180000)
    live_id=page.locator('#run-select').input_value()
    finished=page.request.get(base+'/api/state?run='+live_id).json()
    assert finished['candidates'][0]['physics']['converged']
    assert finished['candidates'][0]['physics']['kappa_w_mk'] is not None
    stages={e['stage'] for e in finished['events']}
    assert {'relaxation','phonons','elasticity','thermal','complete'}<=stages
    assert page.request.get(base+'/api/cif?run='+live_id+'&candidate='+finished['candidates'][0]['id']).status==200
    page.locator('#supercell-button').click()
    assert page.locator('#supercell-button').inner_text()=='1 × 1 × 1'
    page.locator('#supercell-button').click()
    page.locator('#bonds-button').click();page.locator('#bonds-button').click()
    page.locator('#rotate-button').click();page.wait_for_timeout(300);page.locator('#rotate-button').click()
    page.screenshot(path=str(root/'runs/studio-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(600)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1'),'Mobile overflow'
    page.screenshot(path=str(root/'runs/studio-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1600,'height':1200})
    # Exercise stop against a new real worker, then return to the completed result.
    page.locator('#control-button').click()
    page.wait_for_function("document.querySelector('#status').textContent === 'running'",timeout=30000)
    page.locator('#stop-button').click()
    page.wait_for_function("document.querySelector('#status').textContent === 'stopped'",timeout=30000)
    stopped_id=page.locator('#run-select').input_value()
    page.locator('#run-select').select_option(live_id)
    page.wait_for_function("document.querySelector('#status').textContent === 'complete'")
    # Isolated display fixture, intercepted in this browser only; never a campaign result.
    fixture=copy.deepcopy(finished)
    candidate=fixture['candidates'][0]
    candidate['hypothesis']['name']='UI TEST FIXTURE · route rendering'
    candidate['hypothesis']['hypothesis']='Synthetic UI test only. These are not synthesis proposals.'
    candidate['kind']='display_test_fixture'
    methods=['Route graph A','Route graph B','Route graph C']
    candidate['routes']={'routes':[]};candidate['route_assessments']=[]
    for method in methods:
        steps=[{'operation':'Fixture operation '+str(i+1),'target_phase_or_state':phase,'phase_formation_mechanism':'Unverified display fixture',
                'temperature_c':[25,350,100][i],'duration_minutes':20,'pressure_pa':1,'on_device_wafer':True,
                'precursors':['Test precursor'],'equipment':'Fixture equipment','atmosphere':'Test atmosphere','characterization':'Fixture characterization',
                'anticipated_competing_phases':['Unknown'],'stop_or_failure_condition':'Test condition','citations':[]}
               for i,phase in enumerate(['Precursor preparation','Intermediate phase','Target structure'])]
        candidate['routes']['routes'].append({'name':method,'method':'DISPLAY TEST ONLY','phase_selection_hypothesis':'Renderer fixture, not chemical evidence','steps':steps})
        candidate['route_assessments'].append({'route_name':method,'status':'insufficient_evidence','steps':[{'step':i+1,'status':s,'missing_fields':[]} for i,s in enumerate(['unknown','contradicted','unknown'])]})
    route_page=browser.new_page(viewport={'width':1600,'height':1200})
    route_page.on('pageerror',lambda e:errors.append(str(e)))
    route_page.route('**/api/events*',lambda route:route.fulfill(status=200,content_type='text/event-stream',body='data: '+json.dumps(fixture)+'\n\n'))
    route_page.goto(base,wait_until='load')
    route_page.wait_for_selector('.route-node')
    assert route_page.locator('.route-row').count()==3
    assert route_page.locator('.route-node').count()==9
    route_page.locator('.route-node').nth(1).click()
    assert 'Fixture equipment' in route_page.locator('#step-detail').inner_text()
    assert 'Fixture characterization' in route_page.locator('#step-detail').inner_text()
    assert 'contradicted' in route_page.locator('#step-detail').inner_text()
    route_page.screenshot(path=str(root/'runs/studio-route-renderer-fixture.png'),full_page=True)
    route_page.set_viewport_size({'width':390,'height':844});route_page.wait_for_timeout(500)
    assert route_page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1'),'Route graph mobile overflow'
    assert not errors,errors
    browser.close()
    (root/'runs/studio-validation.json').write_text(json.dumps({'live_control_run':live_id,'stopped_run':stopped_id,
        'stages':sorted(stages),'physics':finished['candidates'][0]['physics'],
        'browser_errors':errors,'route_fixture_nodes':9,'mobile_layout':'passed','csrf_rejection':'passed'},indent=2))
print('Passed: real live thermal control, streaming stages, structure controls, CIF export, stop, 3 route graphs / 9 steps, mobile layout, no browser errors')
