"""Read-only final layout check; launches no calculations or model requests."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1200})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8768/',wait_until='load')
    page.wait_for_function("document.querySelector('#crystal').data?.length > 0")
    assert page.locator('#status').inner_text()=='complete'
    assert page.locator('#model').inner_text()=='PET-MAD / 1.0.2'
    assert page.locator('#material-kind').inner_text()=='KNOWN CONTROL'
    assert page.request.get('http://127.0.0.1:8768/api/state',headers={'Host':'untrusted.example'}).status==403
    page.screenshot(path=str(root/'runs/studio-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    page.screenshot(path=str(root/'runs/studio-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
print('Passed: final completed-run selection, control model label, host rejection, desktop/mobile layout')
