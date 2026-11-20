"""Live local Chrome smoke check. Requires playwright and the server on port 8768.

Run from the repository root. Synthetic geometry is UI evidence only.
"""

import hashlib
import json
import struct
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

out = Path(".backend/browser-qa")
out.mkdir(exist_ok=True)
vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
stl = b"Synthetic tetrahedron - UI test only".ljust(80, b"\0") + struct.pack("<I", 4)
for face in faces:
    stl += struct.pack("<12fH", 0, 0, 0, *(v for i in face for v in vertices[i]), 0)
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page.on("pageerror", lambda error: errors.append(str(error)))
    response = page.goto("http://127.0.0.1:8768/web/hackathon.html")
    assert response.status == 200
    expect(page.locator("#inputs-check")).to_have_text("Complete mission inputs")
    for kind in ["fixed-wing", "hybrid", "helicopter", "tiltrotor", "multirotor"]:
        page.locator(f'[data-aircraft="{kind}"]').click()
        expect(page.locator(f'[data-aircraft="{kind}"]')).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#objective")).to_have_value("aero" if kind == "fixed-wing" else "hover")
    page.locator("#example").click()
    expect(page.locator("#inputs-check")).to_have_text("Mission inputs valid")
    page.locator("#payload").fill("-1")
    expect(page.locator("#inputs-check")).to_have_text("Complete mission inputs")
    page.locator("#payload").fill("10")
    page.locator("#geometry-files").set_input_files(
        {"name": "fixture.stl", "mimeType": "model/stl", "buffer": stl}
    )
    expect(page.locator("#geometry-status")).to_contain_text("Select the STL source units")
    page.locator("#geometry-units").select_option("m")
    page.locator("#geometry-files").set_input_files(
        {"name": "fixture.stl", "mimeType": "model/stl", "buffer": stl}
    )
    expect(page.locator("#geometry-status")).to_contain_text("1 STL file(s) loaded")
    expect(page.locator("#geometry-view canvas")).to_be_visible()
    page.get_by_label("Role of fixture.stl", exact=True).select_option("fuselage")
    page.screenshot(path=str(out / "desktop.png"), full_page=True)
    page.locator("#continue").click()
    expect(page.locator("#physics-plan")).to_contain_text("does not execute the solver")
    page.locator("#physics-next").click()
    expect(page.locator("#preflight")).to_contain_text("No solver runs")
    with page.expect_download() as download:
        page.locator("#export").click()
    download.value.save_as(out / "intake.json")
    report = json.loads((out / "intake.json").read_text())
    assert report["declared_inputs"]["payload"] == 10
    assert report["aircraft_configuration"] == "multirotor"
    assert report["geometry"]["files"][0]["sha256_original_bytes"] == hashlib.sha256(stl).hexdigest()
    assert report["geometry"]["files"][0]["triangle_count_preview"] == 4
    assert report["geometry"]["files"][0]["declared_role"] == "fuselage"
    assert report["scientific_status"] == "NOT_SIMULATED"
    assert report["mesh_study"]["solver_runs_completed"] == 0
    page.locator('[data-step="1"]').click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("#geometry-files").set_input_files(
        {
            "name": "empty.stl",
            "mimeType": "model/stl",
            "buffer": b"solid empty\n" + b" " * 100 + b"\nendsolid empty",
        }
    )
    expect(page.locator("#geometry-status")).to_contain_text("Import rejected: STL must contain")
    expect(page.get_by_label("Role of fixture.stl", exact=True)).to_have_value("fuselage")
    invalid = bytearray(stl)
    struct.pack_into("<f", invalid, 96, float("inf"))
    page.locator("#geometry-files").set_input_files(
        {"name": "nonfinite.stl", "mimeType": "model/stl", "buffer": bytes(invalid)}
    )
    expect(page.locator("#geometry-status")).to_contain_text("Import rejected: STL must contain")
    page.locator("#geometry-units").select_option("mm")
    expect(page.locator("#geometry-list")).to_be_empty()
    page.locator("#geometry-files").set_input_files(
        {"name": "fixture.stl", "mimeType": "model/stl", "buffer": stl}
    )
    expect(page.locator("#geometry-status")).to_contain_text("1 STL file(s) loaded")
    page.locator('[data-aircraft="fixed-wing"]').click()
    page.locator("#continue").click()
    expect(page.locator("#physics-plan")).to_contain_text("Unsupported analysis capability")
    page.locator('[data-step="4"]').click()
    expect(page.locator("#step-4")).to_contain_text("No solver results available")
    for focus, model in [
        ("full", "Full analysis: Aero, Propulsion and Structure"),
        ("aero", "Full-aircraft external CFD"),
        ("propulsion", "Propulsion assessment"),
        ("structure", "Structural assessment"),
    ]:
        page.locator('[data-step="1"]').click()
        page.get_by_label("Analysis focus", exact=True).select_option(focus)
        page.locator("#continue").click()
        expect(page.locator("#physics-plan")).to_contain_text(model)
        page.locator("#physics-next").click()
        with page.expect_download() as focus_download:
            page.locator("#export").click()
        focus_download.value.save_as(out / f"intake-{focus}.json")
        exported = json.loads((out / f"intake-{focus}.json").read_text())
        assert exported["objective"] == focus
        assert exported["physics_preflight"]["model"] == model
        assert exported["scientific_status"] == "NOT_SIMULATED"
    page.goto("http://127.0.0.1:8768/web/workbench.html")
    expect(page.locator("body")).to_contain_text("PhysiCore")
    print("PAGE_ERRORS:", errors)
    assert not errors
    browser.close()
print("Browser happy-path checks passed; export verified.")
