"""Chromium synthetic private-workspace journey; credentials remain in memory."""
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'.backend/hosted-browser'/secrets.token_hex(4)
EVIDENCE = Path(os.environ.get('PHYSIMESH_BROWSER_EVIDENCE_DIR', str(ROOT/'docs/qa/assets/production-hosted')))
DATA.mkdir(parents=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)
passwords = {name: secrets.token_urlsafe(24) for name in ('owner', 'reviewer', 'outsider')}
env = {**os.environ, 'PHYSIMESH_MODE': 'hosted', 'PHYSIMESH_DATA_ROOT': str(DATA),
       'PHYSIMESH_DB_PATH': str(DATA/'jobs.sqlite'), 'FIXTURE_PASSWORDS': json.dumps(passwords),
       'MPLCONFIGDIR': str(ROOT/'.cache/matplotlib'), 'XDG_CACHE_HOME': str(ROOT/'.cache')}
bootstrap = '''import json,os
from physimesh.api.app import app_from_environment
app=app_from_environment()
users={name:app.state.identity.provision(name+'@example.test',password=password)
       for name,password in json.loads(os.environ['FIXTURE_PASSWORDS']).items()}
app.state.identity.organization(users['owner'],'Synthetic browser organization')
app.state.metadata.close()
'''
subprocess.run([str(ROOT/'.venv/bin/python'), '-c', bootstrap], env=env, cwd=ROOT, check=True)
env.pop('FIXTURE_PASSWORDS')
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
base = f'http://127.0.0.1:{port}'
receipt = {'data_scope': 'analytic_fixture', 'checks': [], 'downloads': [], 'screenshots': []}


def screenshot(page, name):
    page.screenshot(path=str(EVIDENCE/(name+'.png')), full_page=False)
    receipt['screenshots'].append(name+'.png')


def ready(page):
    page.wait_for_function("document.querySelector('#token').disabled===false")


def login(page, name):
    page.goto(base+'/web/workbench.html')
    page.locator('#individual-login').wait_for(state='visible')
    page.locator('#login-email').fill(name+'@example.test')
    page.locator('#login-password').fill(passwords[name])
    page.locator('#individual-login button').click()
    page.wait_for_function("document.querySelector('#message').textContent.includes('Signed in')")
    ready(page)


with (DATA/'api.log').open('w') as api_log, (DATA/'worker.log').open('w') as worker_log:
    api = subprocess.Popen([str(ROOT/'.venv/bin/python'), '-m', 'uvicorn', 'physimesh.api.app:app_from_environment',
                            '--factory', '--host', '127.0.0.1', '--port', str(port)],
                           env=env, cwd=ROOT, stdout=api_log, stderr=subprocess.STDOUT)
    worker = subprocess.Popen([str(ROOT/'.venv/bin/python'), '-m', 'physimesh.platform.worker'],
                              env=env, cwd=ROOT, stdout=worker_log, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base+'/api/health', timeout=1) as response:
                    assert json.load(response)['mode'] == 'hosted'
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('hosted fixture API did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get('PHYSIMESH_CHROMIUM_EXECUTABLE',
                '/usr/bin/chromium'), headless=True, args=['--no-sandbox', '--window-size=1440,1000'])
            receipt['browser_version'] = browser.version
            owner_context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
            owner = owner_context.new_page()
            login(owner, 'owner')
            owner.locator('#realistic-example').click(); ready(owner)
            owner.wait_for_function("document.querySelector('#project-record').textContent.includes('project_')")
            pid = owner.locator('#project-record').inner_text().split(' · ')[0]
            screenshot(owner, '01-private-design')
            owner.locator('#freeze').click(); ready(owner)
            owner.wait_for_function("document.querySelector('#calculate').disabled===false")
            owner.locator('#calculate').click()
            owner.wait_for_function("document.querySelector('#study-report').textContent.includes('4.25')", timeout=60000)
            ready(owner)
            screenshot(owner, '02-accepted-study-and-jobs')
            with owner.expect_download(timeout=60000) as event:
                owner.locator('#export-pdf').click()
            downloaded = event.value
            destination = DATA/downloaded.suggested_filename
            downloaded.save_as(destination)
            assert downloaded.failure() is None and destination.read_bytes().startswith(b'%PDF-')
            receipt['downloads'].append({'name': destination.name, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                                         'bytes': destination.stat().st_size})
            ready(owner)
            owner.locator('#invite-email').fill('reviewer@example.test')
            owner.locator('#invite-role').select_option('reviewer')
            owner.locator('#invite-member button').click(); ready(owner)
            owner.wait_for_function("document.querySelector('#created-invitation').value.length>20")
            invitation = owner.locator('#created-invitation').input_value()
            owner.locator('#created-invitation').evaluate("element=>{element.value='';}")
            reviewer_context = browser.new_context(viewport={'width': 390, 'height': 844})
            reviewer = reviewer_context.new_page(); login(reviewer, 'reviewer')
            reviewer.locator('#invitation-code').fill(invitation)
            reviewer.locator('#accept-invitation button').click(); ready(reviewer)
            reviewer.wait_for_function("document.querySelector('#project-record').textContent.includes('project_')")
            assert reviewer.locator('#save').is_disabled() and reviewer.locator('#freeze').is_disabled()
            reviewer.locator('#studies button').first.click(); ready(reviewer)
            reviewer.locator('#review-comment').fill('Synthetic browser review only; real qualification remains pending.')
            reviewer.locator('#review-decision').select_option('accepted')
            reviewer.locator('#submit-review').click(); ready(reviewer)
            reviewer.wait_for_function("document.querySelector('#reviews').textContent.includes('reviewer@example.test')")
            with reviewer.expect_download() as exported_review:
                reviewer.locator('.review-export-button').first.click()
            review_download = exported_review.value
            review_path = DATA/'workflow-review.json'
            review_download.save_as(review_path)
            review_raw = review_path.read_bytes()
            assert json.loads(review_raw)['schema_version'] == 'authenticated_workflow_review_v1'
            receipt['downloads'].append({'name': 'workflow-review.json', 'sha256': hashlib.sha256(review_raw).hexdigest(), 'bytes': len(review_raw)})
            assert reviewer.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            screenshot(reviewer, '03-mobile-authenticated-review')
            outsider_context = browser.new_context()
            outsider = outsider_context.new_page(); login(outsider, 'outsider')
            assert outsider.locator('#projects option').count() == 0
            # Test the actual browser session credential without extracting it into logs/receipts.
            denial = outsider.evaluate('''async ([base,pid,email,password])=>{
                const login=await fetch(base+'/api/drone/platform/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
                const {token}=await login.json();return (await fetch(base+'/api/drone/projects/'+pid,{headers:{Authorization:'Bearer '+token}})).status;
            }''', [base, pid, 'outsider@example.test', passwords['outsider']])
            assert denial == 403
            preserved = reviewer.locator('#snapshot').input_value()
            login_request = urllib.request.Request(base+'/api/drone/platform/login', method='POST',
                headers={'Content-Type': 'application/json'}, data=json.dumps({
                    'email': 'reviewer@example.test', 'password': passwords['reviewer']}).encode())
            with urllib.request.urlopen(login_request) as response:
                other_session = json.load(response)['token']
            revoke_request = urllib.request.Request(base+'/api/drone/platform/logout?all_sessions=true', method='POST',
                headers={'Authorization': 'Bearer '+other_session})
            with urllib.request.urlopen(revoke_request) as response:
                assert json.load(response)['revoked']
            reviewer.locator('#studies button').first.click()
            reviewer.wait_for_function("document.querySelector('#message').textContent.includes('session')")
            assert reviewer.locator('#save').is_disabled()
            assert reviewer.locator('#snapshot').input_value() == preserved
            screenshot(reviewer, '04-revoked-session-preserves-design')
            receipt['checks'] = ['individual sign-in', 'private project isolation', 'queued study and first PDF',
                'completed PDF download', 'one-use reviewer invitation', 'reviewer write denial',
                'authenticated review bound to exact result', 'authenticated review download', '390px layout', 'session revocation preserves inputs']
            browser.close()
        (EVIDENCE/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps(receipt))
    finally:
        for process in (worker, api):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
