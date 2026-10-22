"""Read-only browser checks against real saved results; makes no model calls."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1100});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8768/',wait_until='load')
    page.wait_for_function("document.querySelector('#knowledge-summary').textContent.includes('907,259')")
    assert page.locator('#synthesis-pause').is_visible()
    page.locator('#run-select').select_option('20261022-192943-b77799')
    page.wait_for_function("document.querySelector('#critic-content').textContent.includes('Composition mismatch')")
    assert 'WITHHELD INVALID OR UNCONVERGED' in page.locator('#properties').inner_text()
    assert '-17.9' in page.locator('#properties').inner_text()
    assert 'FAILED CHECKS' in page.locator('#material-kind').inner_text()
    assert 'Unused tokens may remain' in page.locator('#budget-explanation').inner_text()
    page.locator('#knowledge-query').fill('SiC');page.locator('#knowledge-form button').click()
    page.wait_for_function("document.querySelector('#knowledge-results').textContent.includes('reference calculations')")
    page.screenshot(path=str(root/'runs/grounded-studio-desktop.png'),full_page=True)
    page.locator('#knowledge-kind').select_option('memory');page.locator('#knowledge-query').fill('boron silicon nitride')
    page.locator('#knowledge-form button').click()
    page.wait_for_function("document.querySelector('#knowledge-results').textContent.includes('Open source')")
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    page.screenshot(path=str(root/'runs/grounded-studio-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
print('Passed: live library counts, synthesis pause, composition audit, withheld properties, instability, budget explanation, both searches, desktop/mobile layout; no model calls')
