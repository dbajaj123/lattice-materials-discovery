"""Browser smoke test for the local, self-contained report (optional Playwright)."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
report = root / "runs/initial/report.html"
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":1100}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(report.as_uri(), wait_until="load")
    page.wait_for_function("document.querySelector('#strength').data !== undefined")
    assert page.locator("#candidate option").count() >= 2
    page.locator("#candidate").select_option("1")
    page.locator("#time").fill("10")
    page.locator("#time").dispatch_event("input")
    assert "h" in page.locator("#time-label").inner_text()
    page.locator("#candidate").select_option(str(page.locator("#candidate option").count()-1))
    assert page.locator("#time").is_disabled()
    assert "not_eligible" in page.locator("#provenance").inner_text() or "Kinetics" in page.locator("#time-label").inner_text()
    page.locator("#candidate").select_option("1")
    case_options = page.locator("#candidate option").all_text_contents()
    case_index = next((i for i,label in enumerate(case_options) if "route_case_study" in label), None)
    if case_index is not None:
        page.locator("#candidate").select_option(str(case_index))
        assert page.locator("#steps tbody tr").count() == 2
    page.screenshot(path=str(root/"runs/initial/dashboard.png"), full_page=True)
    page.set_viewport_size({"width":390,"height":844})
    page.wait_for_timeout(500)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1")
    assert not errors, errors
    browser.close()
    print("Dashboard passed: candidate selection, timeline, unsupported kinetics, mobile layout, no JavaScript errors.")
