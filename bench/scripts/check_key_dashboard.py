"""Test dummy credentials in an isolated studio; never changes the user's keys."""
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

bench=Path(__file__).resolve().parents[1]
python=bench.parent/'.bench-venv/bin/python'
excluded={'OPENAI_API_KEY','ANTHROPIC_API_KEY','GOOGLE_API_KEY','OPENROUTER_API_KEY','MP_API_KEY',
          'MATERIALS_PROJECT_API_KEY','DISCOVERY_MODEL','DISCOVERY_REVIEW_MODEL'}
environment={k:v for k,v in os.environ.items() if k not in excluded}
with tempfile.TemporaryDirectory(prefix='lattice-key-test-') as tmp:
    root=Path(tmp)
    (root/'discovery.json').write_text(json.dumps({'model':'openai/gpt-5.4','network_enabled':False}))
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    process=None
    def launch():
        global process
        process=subprocess.Popen([str(python),'-m','mdb_harness.live_server','--bench',str(root),'--port',str(port)],
                                 env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urlopen(base+'/api/state',timeout=.5) as response: return json.load(response)
            except OSError:
                if process.poll() is not None: raise AssertionError('Isolated studio did not start')
                time.sleep(.2)
        raise AssertionError('Isolated studio timed out')
    def stop():
        if process is not None and process.poll() is None:
            process.terminate();process.wait(timeout=10)
    try:
        launch()
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base,wait_until='load')
            page.wait_for_function("document.querySelector('#credentials').textContent.includes('Key needed')")
            page.locator('#api-key-button').click()
            assert page.locator('#api-key-input').get_attribute('type')=='password'
            assert not page.locator('#persist-key').is_checked()
            dummy='dummy-session-key-not-valid'
            assert page.request.post(base+'/api/credentials',data={'provider':'openai','api_key':dummy}).status==403
            page.locator('#api-key-input').fill(dummy)
            page.locator('#save-api-key').click()
            page.wait_for_function("document.querySelector('#credentials').textContent === 'Key configured'")
            assert page.locator('#api-key-input').input_value()==''
            assert not (root/'.env').exists()
            snapshot=page.request.get(base+'/api/state').text()
            assert dummy not in snapshot
            assert dummy not in page.content()
            assert page.evaluate('localStorage.length')==0
            assert page.evaluate('sessionStorage.length')==0
            assert not list((root/'runs').glob('live/*'))
            stop();assert not launch()['credentials']['present']
            page.reload(wait_until='load')
            page.wait_for_function("document.querySelector('#credentials').textContent.includes('Key needed')")
            page.locator('#api-key-button').click()
            page.locator('#api-key-input').fill('dummy-persistent-key-not-valid')
            page.locator('#persist-key').check();page.locator('#save-api-key').click()
            page.wait_for_function("document.querySelector('#credentials').textContent === 'Key configured'")
            assert stat.S_IMODE((root/'.env').stat().st_mode)==0o600
            stop();assert launch()['credentials']['present']
            page.reload(wait_until='load')
            page.wait_for_function("document.querySelector('#credentials').textContent === 'Key configured'")
            page.locator('#api-key-button').click()
            assert page.locator('#api-key-input').input_value()==''
            assert 'A key is configured' in page.locator('#key-status').inner_text()
            page.screenshot(path=str(bench/'runs/api-key-panel.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            page.locator('#api-key-input').fill('cleared-on-close-test-key')
            page.keyboard.press('Escape')
            page.wait_for_function("!document.querySelector('#api-key-dialog').open && document.querySelector('#api-key-input').value === ''")
            assert page.locator('#api-key-input').input_value()==''
            assert not errors,errors
            browser.close()
    finally: stop()
print('Passed: isolated session/local key storage, restart behavior, masked input, clearing, no key disclosure or browser storage, CSRF, mobile layout; no provider calls')
