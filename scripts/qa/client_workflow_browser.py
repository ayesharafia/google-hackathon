"""Synthetic client-workflow browser regressions; no screenshots, video or private sources.

Run with the installed test environment. Optional --receipt exclusively creates a
sanitized JSON receipt; existing receipts are never replaced. This helper starts
only disposable loopback API processes and never targets reserved port 3737.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
RESERVED_PORT = 3737
PRIVATE_BOOTSTRAP = """
import os
import uvicorn
from physimesh.api.app import app_from_environment
app = app_from_environment()
identity = app.state.identity
user = identity.provision('client-workflow@example.test', password=os.environ.pop('CLIENT_QA_PASSWORD'))
identity.organization(user, 'Synthetic organization A')
identity.organization(user, 'Synthetic organization B')
uvicorn.run(app, host='127.0.0.1', port=int(os.environ['CLIENT_QA_PORT']))
"""


def free_port():
    for _ in range(20):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        if port != RESERVED_PORT:
            return port
    raise RuntimeError('no eligible ephemeral port')


@contextlib.contextmanager
def server(root: Path, *, private=False):
    port = free_port()
    token, password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('PHYSIMESH_', 'CLIENT_QA_'))}
    env.update(PHYSIMESH_DATA_ROOT=str(root), PHYSIMESH_DB_PATH=str(root/'jobs.sqlite'),
               PHYSIMESH_MODE='hosted' if private else 'local', PHYSIMESH_API_TOKEN=token,
               MPLCONFIGDIR=str(root/'matplotlib'), XDG_CACHE_HOME=str(root/'cache'))
    if private:
        env.update(CLIENT_QA_PASSWORD=password, CLIENT_QA_PORT=str(port))
        command = [sys.executable, '-c', PRIVATE_BOOTSTRAP]
    else:
        command = [sys.executable, '-m', 'uvicorn', 'physimesh.api.app:app_from_environment',
                   '--factory', '--host', '127.0.0.1', '--port', str(port)]
    root.mkdir(parents=True)
    with (root/'api.log').open('w') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            base = f'http://127.0.0.1:{port}'
            for _ in range(200):
                try:
                    with urllib.request.urlopen(base+'/api/health', timeout=.5) as response:
                        health = json.load(response)
                    if health.get('status') == 'ok':
                        break
                except OSError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError('disposable API exited during startup')
                time.sleep(.1)
            else:
                raise RuntimeError('disposable API startup timeout')
            yield base, token, password
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def api(base, token, path, *, method='GET', body=None):
    request = urllib.request.Request(base+'/api/drone'+path, method=method,
                                    headers={'Authorization': 'Bearer '+token,
                                             'Content-Type': 'application/json'},
                                    data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def ready(page):
    # This tracks the action's controls; detached layout/summary rendering has
    # its own observable assertions at each dependent interaction below.
    expect(page.locator('#connection button')).to_be_enabled(timeout=60_000)


def click(page, selector):
    page.locator(selector).click()
    ready(page)


def edit_snapshot(page, snapshot):
    area = page.locator('#snapshot')
    page.get_by_text('Design input JSON', exact=True).click() if not area.is_visible() else None
    area.fill(json.dumps(snapshot))
    area.press('Tab')


def local_journey(browser, root, checks):
    with server(root) as (base, token, _), browser.new_context() as context:
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda _: errors.append('pageerror'))
        page.goto(base+'/web/workbench.html')
        page.locator('#token').fill(token)
        click(page, '#connection button')
        assert page.locator('#token').input_value() == ''
        click(page, '#realistic-example')
        original = json.loads(page.locator('#snapshot').input_value())
        project = page.locator('#projects').input_value()
        click(page, '#freeze')
        with page.expect_response(lambda response: response.url.endswith('/studies')
                                  and response.request.method == 'POST') as response:
            click(page, '#calculate')
        retained = response.value.json()
        assert retained['outcome'] == 'feasible'
        digest = retained['study_sha256']
        page.wait_for_function('document.querySelector("#study-summary").textContent.includes("Nominal")')
        assert 'Scenario' in page.locator('#study-summary').inner_text()
        assert 'allowable' in page.locator('#study-summary').inner_text().lower()
        checks.append('distinct_retained_summary_bounds')

        changed = json.loads(json.dumps(original))
        old_x = changed['rotors'][0]['center_body_m'][0]
        changed['rotors'][0]['center_body_m'][0] = old_x+2.125
        changed['rotors'][0]['map_ref'] = '0'*64
        edit_snapshot(page, changed)
        selector = f'#studies button[data-study="{digest}"]'
        click(page, selector)
        page.get_by_text('Displayed geometry and rotor inputs', exact=True).click()
        rotor = page.locator('#layout-inputs p[data-rotor-id='+json.dumps(original['rotors'][0]['rotor_id'])+']')
        expect(rotor).to_be_visible()
        expect(rotor).to_contain_text('centre [')
        expect(rotor).to_contain_text(original['rotors'][0]['map_ref'])
        displayed_centre = rotor.inner_text().split('centre [')[1].split(']')[0]
        assert [float(value) for value in displayed_centre.split(', ')] == original['rotors'][0]['center_body_m']
        assert original['rotors'][0]['map_ref'] in page.locator('#layout-inputs').inner_text()
        assert '0'*64 not in page.locator('#layout-inputs').inner_text()
        assert json.loads(page.locator('#snapshot').input_value()) == changed
        assert retained['specification']['revision_sha256'] in page.locator('#display-context').inner_text()
        checks.append('historical_study_uses_frozen_rotor_inputs_preserves_unsaved_draft')
        choices = page.locator('#view-case option').all()
        assert len(choices) >= 2
        case_id = choices[-1].get_attribute('value')
        page.locator('#view-case').select_option(case_id)
        page.wait_for_function('(id)=>document.querySelector("#layout-note").textContent.includes(id)',
                               arg=case_id)
        checks.append('selected_case_context')
        click(page, '#show-draft-layout')
        expect(page.locator('#display-context')).to_contain_text('unsaved')
        expect(rotor).to_contain_text(str(old_x+2.125))
        expect(rotor).to_contain_text('0'*64)
        assert str(old_x+2.125) in page.locator('#layout-inputs').inner_text()
        assert '0'*64 in page.locator('#layout-inputs').inner_text()
        assert json.loads(page.locator('#snapshot').input_value()) == changed
        checks.append('draft_view_restores_unsaved_rotor_inputs')

        summary_url = '**/studies/*/summary'
        page.route(summary_url, lambda route: route.fulfill(status=503, content_type='application/json',
                                                           body='{"detail":"Synthetic unavailable"}'))
        click(page, selector)
        expect(page.locator('#study-summary')).to_contain_text('unavailable')
        assert 'kg' not in page.locator('#study-summary').inner_text()
        assert page.locator('#export-study').is_enabled()
        assert page.locator('#export-pdf').is_enabled()
        assert page.locator('#study-report').inner_text()
        page.unroute(summary_url)
        checks.append('summary_failure_withholds_bounds_preserves_details_and_exports')

        saved = api(base, token, '/projects/'+project)
        remote = json.loads(saved['snapshot_json'])
        remote['identity']['description'] = 'Synthetic remote conflict edit'
        api(base, token, '/projects/'+project+'/draft', method='PUT',
            body={'expected_version': saved['draft_version'], 'snapshot_json': json.dumps(remote)})
        page.locator('#save').click()
        page.locator('#draft-conflict').wait_for(state='visible')
        assert json.loads(page.locator('#snapshot').input_value()) == changed
        click(page, '#conflict-keep')
        assert json.loads(page.locator('#snapshot').input_value()) == changed
        page.locator('#save').click()
        page.locator('#draft-conflict').wait_for(state='visible')
        click(page, '#conflict-reload')
        page.wait_for_function('(description)=>JSON.parse(document.querySelector("#snapshot").value)'
                               '.identity.description===description', arg=remote['identity']['description'])
        assert json.loads(page.locator('#snapshot').input_value()) == remote
        checks.append('draft_conflict_keep_and_explicit_replace')
        assert not errors


def private_journey(browser, root, checks):
    with server(root, private=True) as (base, _, password), browser.new_context() as context:
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda _: errors.append('pageerror'))
        page.goto(base+'/web/workbench.html')
        page.locator('#individual-login').wait_for(state='visible')
        page.locator('#login-email').fill('client-workflow@example.test')
        page.locator('#login-password').fill(password)
        click(page, '#individual-login button')
        page.wait_for_function('document.querySelector("#organization").options.length===2')
        click(page, '#example')
        original = json.loads(page.locator('#snapshot').input_value())
        original['identity']['description'] = 'Synthetic unsaved private draft'
        edit_snapshot(page, original)
        old_org = page.locator('#organization').input_value()
        next_org = next(option.get_attribute('value') for option in page.locator('#organization option').all()
                        if option.get_attribute('value') != old_org)
        page.once('dialog', lambda dialog: dialog.dismiss())
        page.locator('#organization').select_option(next_org)
        assert page.locator('#organization').input_value() == old_org
        assert json.loads(page.locator('#snapshot').input_value()) == original
        checks.append('dirty_organization_switch_cancel_preserves_draft')
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#organization').select_option(next_org)
        ready(page)
        expect(page.locator('#snapshot')).to_have_value('')
        assert page.locator('#snapshot').input_value() == ''
        assert 'No project' in page.locator('#display-context').inner_text()
        assert page.locator('#layout-inputs').inner_text() == ''
        assert page.locator('#study-summary').inner_text() == ''
        checks.append('confirmed_organization_switch_clears_context')
        click(page, '#example')
        edited = json.loads(page.locator('#snapshot').input_value())
        edited['identity']['description'] = 'Synthetic unsaved logout draft'
        edit_snapshot(page, edited)
        page.once('dialog', lambda dialog: dialog.dismiss())
        page.locator('#logout').click()
        assert json.loads(page.locator('#snapshot').input_value()) == edited
        assert page.locator('#individual-session').is_visible()
        checks.append('dirty_logout_cancel_preserves_draft')
        page.once('dialog', lambda dialog: dialog.accept())
        click(page, '#logout')
        expect(page.locator('#snapshot')).to_have_value('')
        assert page.locator('#snapshot').input_value() == ''
        assert page.locator('#individual-session').is_hidden()
        assert page.locator('#layout-inputs').inner_text() == ''
        checks.append('confirmed_logout_clears_project_context')
        assert not errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, help='New sanitized JSON receipt (never overwritten)')
    args = parser.parse_args()
    if args.receipt and args.receipt.exists():
        parser.error('receipt already exists')
    receipt = {'schema_version': 'client_workflow_browser_v1', 'data_scope': 'analytic_fixture',
               'status': 'failed', 'checks': [], 'media_captured': False,
               'qualification': 'Synthetic browser workflow checks only; no engineering or production acceptance.'}
    phase = 'startup'
    try:
        with tempfile.TemporaryDirectory(prefix='client-workflow-qa-') as temporary, sync_playwright() as playwright:
            executable = os.environ.get('PHYSIMESH_CHROMIUM_EXECUTABLE') or shutil.which('google-chrome') or shutil.which('chromium')
            browser = playwright.chromium.launch(executable_path=executable, headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            try:
                receipt['browser_version'] = browser.version
                phase = 'local_workflow'
                local_journey(browser, Path(temporary)/'local', receipt['checks'])
                phase = 'private_context_transitions'
                private_journey(browser, Path(temporary)/'private', receipt['checks'])
            finally:
                browser.close()
        receipt['status'] = 'passed'
    except (AssertionError, BrowserError, OSError, RuntimeError, ValueError, TypeError, KeyError, IndexError,
            subprocess.SubprocessError) as error:
        receipt['failure'] = {'phase': phase, 'type': type(error).__name__}
        trace = error.__traceback__
        while trace:
            if trace.tb_frame.f_code.co_filename == __file__:
                receipt['failure']['helper_line'] = trace.tb_lineno
            trace = trace.tb_next
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open('x') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
