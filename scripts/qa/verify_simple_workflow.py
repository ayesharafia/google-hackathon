"""Exercise the new workflow against the local server using installed Chrome."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright

out = Path(".backend/browser-qa/simple-workflow")
out.mkdir(parents=True, exist_ok=True)
errors, api_requests = [], []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: api_requests.append(request.url) if "/api/" in request.url else None)
    page.goto("http://127.0.0.1:8768/web/hackathon.html")
    page.locator('[data-step="3"]').click()
    page.get_by_role("link", name="Open simple workflow").click()
    expect(page).to_have_url("http://127.0.0.1:8768/web/simple-workflow.html")
    expect(page.locator("[data-step]")).to_have_count(3)
    expect(page.locator('a[href="/web/workbench.html"]')).to_have_count(0)
    expect(page.locator('a[href="/web/results.html"]')).to_have_count(0)
    expect(page.locator("#payload")).to_have_value("300")
    for kind in ["multirotor", "hybrid", "helicopter", "tiltrotor"]:
        page.locator(f'[data-aircraft="{kind}"]').click()
        expect(page.locator("#fixed-wing-launch")).to_be_hidden()
        page.locator("#continue").click()
        expect(page.locator('[data-calculation="aero"]')).to_be_hidden()
        page.locator("#physics-back").click()
    page.locator('[data-aircraft="fixed-wing"]').click()
    page.get_by_label("Analysis focus", exact=True).select_option("full")
    for name, value in [("payload", "25"), ("altitude", "500"), ("speed", "40"), ("duration", "90")]:
        page.locator("#" + name).fill(value)
    page.screenshot(path=str(out / "configure.png"), full_page=True)
    page.locator("#continue").click()
    expect(page.locator("#mission-summary")).to_contain_text("Fixed-wing")
    expect(page.locator("#mission-summary")).to_contain_text("25 kg")
    expect(page.locator("#mission-summary")).to_contain_text("90 min")
    expect(page.locator("#physics-plan")).to_contain_text("Aero, Propulsion and Structure")
    page.screenshot(path=str(out / "review.png"), full_page=True)
    page.locator("#physics-back").click()
    expect(page.locator("#payload")).to_have_value("25")
    page.locator("#payload").fill("30")
    page.locator("#continue").click()
    expect(page.locator("#mission-summary")).to_contain_text("30 kg")
    page.locator("#physics-next").click()
    expect(page.locator("#preflight")).to_contain_text("Flight outcome: Not determined")
    expect(page.locator("#preflight")).to_contain_text(
        "A complete aircraft flight simulation has not been run"
    )
    expect(page.locator("#export")).to_have_count(0)
    expect(page.get_by_role("heading", name="Next action", exact=True)).to_have_count(0)
    page.screenshot(path=str(out / "outcome-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "export-phone.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.reload()
    expect(page.locator("#payload")).to_have_value("300")
    assert not errors, errors
    assert all("/api/session" in url for url in api_requests), api_requests
    browser.close()
print(
    "Simple workflow passed: entry, three steps, review/edit, outcome-only output, reset; no project API requests or page errors."
)
