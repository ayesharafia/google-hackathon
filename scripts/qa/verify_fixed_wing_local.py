"""Exercise the fixed-wing button using labelled synthetic inputs, never aircraft approval."""
import json
import runpy
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from physimesh.drone.provenance import sha256_record

root = Path(__file__).resolve().parents[2]
body = runpy.run_path(str(root / 'tests/drone/test_fixed_wing.py'))['request']()
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8768/web/simple-workflow.html')
    page.locator('#setup-fixed-wing').click()
    panel = page.locator('[data-calculation="aero"]')
    expect(panel).to_have_attribute('open', '')
    run = panel.locator('[data-run="aero"]')
    expect(page.locator('#calculation-token')).to_have_count(0)
    expect(page.get_by_role('button', name='Connect', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Disconnect', exact=True)).to_have_count(0)
    expect(run).to_be_enabled()
    for name, value in body.items():
        if name in ('configuration', 'evaluation'):
            continue
        items = [(f'{name}.{k}', v) for k, v in value.items()] if isinstance(value, dict) else [(name, value)]
        for field, number in items:
            panel.locator(f'[data-field="{field}"]').fill(str(number))
    with page.expect_response('**/api/drone/fixed-wing/screen') as response:
        run.click()
    assert 'authorization' not in response.value.request.all_headers()
    result = response.value.json()
    expect(panel.locator('.component-result')).to_be_visible()
    assert result['outputs']['lift_n'] == 7500
    assert result['inputs'] == body
    assert result['input_sha256'] == sha256_record(result['inputs'])
    digest = result.pop('evaluation_sha256')
    assert digest == sha256_record(result)
    assert result['aircraft_status'] is None
    panel.locator('[data-field="airspeed_m_s"]').fill('51')
    expect(panel.locator('.component-result')).to_be_hidden()
    panel.locator('[data-field="span_efficiency"]').fill('0')
    run.click()
    expect(panel).to_contain_text('Not computed:')
    page.reload()
    page.locator('#setup-fixed-wing').click()
    expect(page.locator('[data-run="aero"]')).to_be_enabled()
    assert page.evaluate('localStorage.length') == 0
    assert not errors, errors
    print(json.dumps({'browser': 'Chrome', 'fixed_wing_button': 'PASS', 'synthetic_lift_n': 7500, 'aircraft_validated': False}))
    browser.close()
