"""Browser regression against the local studio. No model calls; restores settings."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
base='http://127.0.0.1:8768'
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1100})
    errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
    page.goto(base,wait_until='load')
    page.wait_for_function("document.querySelector('#knowledge-summary').textContent.includes('reference records')")
    state=page.request.get(base+'/api/state').json()
    original=state['settings']
    token=page.locator('meta[name="studio-token"]').get_attribute('content')
    try:
        page.locator('#settings-button').click()
        page.locator('[name=model]').fill('openai/gpt-6-luna')
        page.locator('[name=review_model]').fill('openai/gpt-6-astra')
        page.locator('[name=thermal_max_displacements]').fill('500')
        page.locator('#settings-form [type=submit]').click()
        page.wait_for_function("!document.querySelector('#settings-dialog').open")
        page.reload(wait_until='load')
        page.wait_for_function("document.querySelector('#knowledge-summary').textContent.includes('reference records')")
        page.locator('#settings-button').click()
        assert page.locator('[name=model]').input_value()=='openai/gpt-6-luna'
        assert page.locator('[name=review_model]').input_value()=='openai/gpt-6-astra'
        assert page.locator('[name=thermal_max_displacements]').input_value()=='500'
        page.locator('[name=model]').fill('unsupported/model')
        page.locator('#settings-form [type=submit]').click()
        page.locator('#settings-error').wait_for(state='visible')
        assert 'provider/model-id' in page.locator('#settings-error').inner_text()
        page.locator('#close-settings').click()
        page.locator('#api-key-button').click()
        assert page.locator('#key-provider option').count()==5
        page.locator('#close-api-key').click()
        page.locator('#run-select').select_option('20261022-201323-13ab62')
        page.wait_for_function("document.querySelector('#properties').textContent.includes('DISABLED BY CONFIGURATION')")
        assert page.locator('#synthesis-pause').is_visible()
        page.locator('summary',has_text='What can we test?').click()
        assert 'not connected' in page.locator('#capabilities').inner_text()
        assert 'Synthesis is paused.' in page.locator('#route-map').inner_text()
        page.screenshot(path=str(root/'runs/model-settings-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#settings-button').click()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
        page.screenshot(path=str(root/'runs/model-settings-mobile.png'),full_page=True)
        assert not errors,errors
    finally:
        response=page.request.post(base+'/api/settings',data=original,
            headers={'X-Studio-Token':token,'Origin':base})
        assert response.ok,'Original settings must be restored'
        browser.close()
print('Passed: persisted proposer/critic settings, validation, all key providers, capability panel, synthesis pause, desktop/mobile; no model calls.')
