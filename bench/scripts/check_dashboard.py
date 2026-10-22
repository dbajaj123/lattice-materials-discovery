"""Browser integration test for public-release audit and crystal inspection."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto((root/'runs/report.html').as_uri(),wait_until='load')
    page.wait_for_function("document.querySelector('#crystal').data !== undefined")
    assert page.locator('#candidate option').count()==531
    page.locator('#candidate').select_option(index=10)
    page.wait_for_function("document.querySelector('#recipe').textContent.length > 0")
    assert 'Published verdict:' in page.locator('#verdict').inner_text()
    assert page.evaluate("document.querySelector('#crystal').data.length > 0")
    page.screenshot(path=str(root/'runs/dashboard.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
    assert not errors,errors
    browser.close()
print('Passed: released rows, crystal rendering, candidate switching, mobile width, no JS errors')
