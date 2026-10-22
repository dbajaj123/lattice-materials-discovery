"""Browser check of prepared campaign and the explicitly scripted test fixture."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
fixture=root/'runs/test-artifacts/test_entire_campaign_multiple_0/campaign/report.html'
prepared=root/'runs/discovery/report.html'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(fixture.as_uri(),wait_until='load')
    page.wait_for_function("document.querySelector('#crystal').data !== undefined")
    assert page.locator('#candidate option').count()==1
    assert page.locator('#routes h3').count()==3
    assert 'Known silicon tests orchestration only' in page.locator('#hypothesis').inner_text()
    assert page.locator('#routes').inner_text().count('insufficient_evidence')>=3
    page.screenshot(path=str(root/'runs/campaign-integration-test.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'),'Fixture overflows mobile viewport'
    page.goto(prepared.as_uri(),wait_until='load')
    assert page.locator('#candidate option').count()==0
    assert 'model key' in page.locator('#empty').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'),'Prepared report overflows mobile viewport'
    page.set_viewport_size({'width':1440,'height':1100})
    page.screenshot(path=str(root/'runs/discovery/dashboard.png'),full_page=True)
    assert not errors,errors
    browser.close()
print('Passed: crystal rendering, three route cards, uncertainty labels, prepared state, mobile layout, no JS errors')
