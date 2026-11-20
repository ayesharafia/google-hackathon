"""Real local API/browser integration using explicitly synthetic model fixtures."""

import json
import math
import runpy
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from physimesh.drone.provenance import sha256_record

root = Path(__file__).resolve().parents[2]
out = root / ".backend/browser-qa/calculations"
out.mkdir(parents=True, exist_ok=True)
fixtures = {
    "aero": runpy.run_path(str(root / "tests/drone/test_fixed_wing.py"))["request"](),
    "structure": runpy.run_path(str(root / "tests/drone/test_cantilever_application.py"))["request"](),
    "propulsion": runpy.run_path(str(root / "tests/drone/test_hover_bemt_application.py"))["request"](),
}
errors, requests = [], []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.goto("http://127.0.0.1:8768/web/simple-workflow.html")
    page.locator('[data-aircraft="fixed-wing"]').click()
    page.get_by_label("Analysis focus", exact=True).select_option("full")
    page.locator("#example").click()
    page.locator("#speed").fill("70")
    page.locator("#continue").click()
    expect(page.locator('[data-run="aero"]')).to_be_disabled()
    page.locator("#calculation-token").fill("wrong-token")
    page.get_by_role("button", name="Connect", exact=True).click()
    expect(page.locator(".calculation-access")).to_contain_text("Development access token")
    expect(page.locator('[data-run="aero"]')).to_be_disabled()
    page.locator("#calculation-token").fill((root / ".backend/local-hackathon/dev-token.txt").read_text())
    page.get_by_role("button", name="Connect", exact=True).click()
    expect(page.locator("#component-calculations")).to_contain_text("Connected to local calculations.")
    for key, body in fixtures.items():
        panel = page.locator(f'[data-calculation="{key}"]')
        panel.locator("summary").click()
        for name, value in body.items():
            if name in ("evaluation", "configuration"):
                continue
            items = (
                [(f"{name}.{k}", v) for k, v in value.items()] if isinstance(value, dict) else [(name, value)]
            )
            for field, number in items:
                control = panel.locator(f'[data-field="{field}"]')
                if field == "twist_law":
                    control.select_option(number)
                else:
                    control.fill("" if number is None else str(number))
        panel.locator(f'[data-run="{key}"]').click()
        expect(panel.locator(".component-result")).to_be_visible()
        with page.expect_download() as download:
            panel.get_by_role("button", name="Download exact component result").click()
        download.value.save_as(out / f"{key}.json")
        result = json.loads((out / f"{key}.json").read_text())
        assert result["inputs"] == body
        assert result["input_sha256"] == sha256_record(result["inputs"])
        expected = result.pop("evaluation_sha256")
        assert expected == sha256_record(result)
        assert result["evidence_level"] == "unverified"
        assert result["aircraft_status"] is None
        if key == "aero":
            assert result["outputs"]["lift_n"] == 7500
        if key == "structure":
            assert math.isclose(result["outputs"]["tip_deflection_m"], 0.0000215)
        if key == "propulsion":
            assert result["status"] == "COMPUTED_EXPERIMENTAL"
            assert result["physical_validation"] == "NOT_ESTABLISHED"
        panel.locator(".component-result").screenshot(path=str(out / f"{key}-result.png"))
        panel.locator("summary").click()
    page.locator('[data-step="1"]').click()
    expect(page.locator('#speed')).to_have_value('70')
    page.locator('#speed').fill('80')
    page.locator('#continue').click()
    expect(page.locator('[data-calculation="aero"] [data-field="airspeed_m_s"]')).to_have_value('50.0')
    page.locator("#physics-next").click()
    expect(page.locator("#preflight")).to_contain_text("Flight outcome: Not determined")
    expect(page.locator("#export")).to_have_count(0)
    page.locator('[data-step="2"]').click()
    panel = page.locator('[data-calculation="structure"]')
    panel.locator("summary").click()
    panel.locator('[data-field="length_m"]').fill("3")
    expect(panel.locator(".component-result")).to_be_hidden()
    panel.locator('[data-field="length_m"]').fill("0")
    panel.locator('[data-run="structure"]').click()
    expect(panel.locator('[role="status"]')).to_contain_text("Not computed:")
    expect(panel.locator(".component-result")).to_be_hidden()
    page.locator("#physics-next").click()
    expect(page.locator("#preflight")).to_contain_text("some component checks could not be completed")
    expect(page.locator("#preflight")).to_contain_text("structure:")
    page.locator('[data-step="2"]').click()
    panel.locator('[data-field="length_m"]').fill("3")

    def corrupt_units(route):
        response = route.fetch()
        data = response.json()
        data["output_units"]["tip_deflection_m"] = "mm"
        route.fulfill(response=response, json=data)

    page.route("**/api/drone/cantilever/screen", corrupt_units)
    panel.locator('[data-run="structure"]').click()
    expect(panel.locator('[role="status"]')).to_contain_text("invalid response")
    expect(panel.locator(".component-result")).to_be_hidden()
    page.unroute("**/api/drone/cantilever/screen", corrupt_units)
    # Hold the real response in-browser, edit while it is pending, then release.
    page.evaluate("""() => { const original=window.fetch; window.fetch=async(...args)=>{
      const response=await original(...args); if(String(args[0]).endsWith('/cantilever/screen')){
        await new Promise(resolve=>window.releaseCalculation=resolve);
      } return response; }; }""")
    panel.locator('[data-run="structure"]').click()
    page.wait_for_function('typeof window.releaseCalculation === "function"')
    panel.locator('[data-field="length_m"]').fill("4")
    page.evaluate("window.releaseCalculation()")
    expect(panel.locator(".component-result")).to_be_hidden()
    page.get_by_role("button", name="Disconnect", exact=True).click()
    expect(page.locator('[data-run="structure"]')).to_be_disabled()
    page.screenshot(path=str(out / "desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "phone.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    assert not any("/projects" in url for url in requests)
    browser.close()
print(
    "PASS: three real component calculations, exact exports/hashes, analytical checks, auth, edit invalidation, delayed response and disconnect; no project mutation requests."
)
