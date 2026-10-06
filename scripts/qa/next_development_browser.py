"""Reproducible Chromium acceptance against a fresh local server, using synthetic inputs.

Run with a Python containing playwright. No token is printed or retained. Runtime
DB/downloads/video are ignored under .backend; screenshots and receipt are retained.
This is application QA, not a substitute for independent physics or client review.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.backend' / 'next-development-browser' / secrets.token_hex(4)
EVIDENCE = Path(os.environ.get('PHYSIMESH_BROWSER_EVIDENCE_DIR', str(ROOT/'docs/qa/assets/next-development')))
RUNTIME.mkdir(parents=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)
TOKEN = secrets.token_urlsafe(32)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    PORT = sock.getsockname()[1]
BASE = f'http://127.0.0.1:{PORT}'
ENV = {**os.environ, 'PHYSIMESH_DATA_ROOT': str(RUNTIME),
       'PHYSIMESH_API_TOKEN': TOKEN, 'PHYSIMESH_MODE': 'local',
       'PHYSIMESH_DB_PATH': str(RUNTIME/'jobs.sqlite'), 'MPLCONFIGDIR': str(ROOT/'.cache/matplotlib'),
       'XDG_CACHE_HOME': str(ROOT/'.cache')}
RECEIPT = {'browser': 'system Chromium', 'data_scope': 'analytic_fixture',
           'checks': [], 'rehearsals_s': [], 'downloads': [], 'screenshots': []}


def api(path, method='GET', body=None, raw=False):
    request = urllib.request.Request(BASE+'/api/drone'+path, method=method,
                                    headers={'Authorization': 'Bearer '+TOKEN,
                                             'Content-Type': 'application/json'},
                                    data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    return data if raw else json.loads(data)


def shot(page, name, selector=None):
    filename = name+'.png'
    target = page.locator(selector) if selector else page
    target.screenshot(path=str(EVIDENCE/filename))
    RECEIPT['screenshots'].append(filename)


def click(page, selector):
    page.locator(selector).click()
    page.wait_for_function("!document.querySelector('#token').disabled")
    assert 'error' not in (page.locator('#message').get_attribute('class') or ''), page.locator('#message').inner_text()


def current(page):
    return api('/projects/'+page.locator('#projects').input_value())


def run(page):
    click(page, '#freeze')
    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/studies')) as response:
        click(page, '#calculate')
    assert response.value.status == 200
    return response.value.json()


def download(page, button, suffix):
    with page.expect_download() as expected:
        page.locator(button).click()
    item = expected.value
    assert item.failure() is None
    path = RUNTIME/(suffix+'-'+item.suggested_filename)
    item.save_as(path)
    content = path.read_bytes()
    RECEIPT['downloads'].append({'name': path.name, 'bytes': len(content),
                                 'sha256': hashlib.sha256(content).hexdigest()})
    page.wait_for_function("!document.querySelector('#token').disabled")
    return content


with (RUNTIME/'server.log').open('w') as log:
    process = subprocess.Popen([str(ROOT/'.venv/bin/python'), '-m', 'uvicorn',
                                'physimesh.api.app:app_from_environment', '--factory',
                                '--host', '127.0.0.1', '--port', str(PORT)], cwd=ROOT, env=ENV,
                               stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(BASE+'/api/health', timeout=1) as response:
                    assert json.load(response)['status'] == 'ok'
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError('Fresh server failed; inspect ignored server.log')
                time.sleep(.1)
        else:
            raise RuntimeError('Server startup timed out')
        with tempfile.TemporaryDirectory(prefix='physicore-browser-') as profile, sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(profile, executable_path=os.environ.get('PHYSIMESH_CHROMIUM_EXECUTABLE', '/usr/bin/chromium'), headless=True,
                no_viewport=True, reduced_motion='reduce',
                args=['--no-sandbox', '--disable-dev-shm-usage', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
                      '--window-size=1440,1000'])
            page = context.new_page()
            frames = []
            frame_dir = RUNTIME/'frames'
            frame_dir.mkdir()
            cdp = context.new_cdp_session(page)
            def record_frame(event):
                cdp.send('Page.screencastFrameAck', {'sessionId': event['sessionId']})
                path = frame_dir/f'{len(frames):06d}.jpg'
                path.write_bytes(base64.b64decode(event['data']))
                frames.append((path, event['metadata']['timestamp']))
            cdp.on('Page.screencastFrame', record_frame)
            cdp.send('Page.startScreencast', {'format':'jpeg', 'quality':65, 'maxWidth':1440, 'maxHeight':1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE+'/web/workbench.html')
            page.locator('#token').fill(TOKEN)
            click(page, '#connection button')
            assert page.locator('#token').input_value() == ''
            shot(page, '01-connected')
            click(page, '#realistic-example')
            page.wait_for_function("document.querySelector('#layout-view canvas') !== null")
            shot(page, '02-synthetic-layout', '#layout-title + div')
            # Exercise explicit conditioning policy validation and binding.
            snap = json.loads(page.locator('#snapshot').input_value())
            source = api('/projects/performance-sources/'+snap['rotors'][0]['map_ref'])
            raw_digest = source['conditioning']['raw_source_sha256']
            page.get_by_text('Condition a retained rotor map', exact=True).click()
            page.get_by_label('Raw map SHA-256', exact=True).fill(raw_digest)
            page.get_by_role('button', name='Condition retained map', exact=True).click()
            policy_box = page.locator('details').filter(has=page.locator('summary').filter(has_text='Condition a retained rotor map'))
            policy_box.get_by_role('status').wait_for(state='visible')
            page.wait_for_function("[...document.querySelectorAll('details')].find(d=>d.querySelector('summary')?.textContent==='Condition a retained rotor map').querySelector('[role=status]').textContent.includes('policy')")
            page.get_by_label('Policy source', exact=True).fill(source['conditioning']['policy']['source_note'])
            for label, value in [('Maximum relative torque-fit residual', .08), ('Power relative uncertainty bound', .01), ('Torque relative uncertainty bound', .01), ('Maximum hull shift / peak envelope power', .25)]:
                page.get_by_label(label, exact=True).fill(str(value))
            page.get_by_role('button', name='Condition retained map', exact=True).click()
            page.wait_for_function("[...document.querySelectorAll('details')].find(d=>d.querySelector('summary')?.textContent==='Condition a retained rotor map').querySelector('[role=status]').textContent.startsWith('Raw ')")
            shot(page, '09-explicit-conditioning', '#input-editors details:nth-last-of-type(4)')

            # The binding action is explicit, and only applies to raw-matching rotors.
            page.get_by_text('Rotors and retained performance sources', exact=True).click()
            for control in page.get_by_label('Retained map SHA-256', exact=True).all():
                control.fill(raw_digest)
            page.get_by_role('button', name='Bind conditioned map to matching rotors', exact=True).click()
            rebound = json.loads(page.locator('#snapshot').input_value())
            assert all(r['map_ref'] == source['conditioning']['conditioned_source_sha256'] for r in rebound['rotors'])
            click(page, '#save')
            RECEIPT['checks'].append('Blank conditioning policy refuses; explicit sourced tolerances condition and bind matching raw-map rotors')
            study = run(page)
            assert study['schema_version'] == 'local_mission_capacity_v4' and study['outcome'] == 'feasible'
            shot(page, '03-capacity-result', '#study-report')
            pid = current(page)['project_id']
            exact = download(page, '#export-study', 'initial')
            assert exact == api(f"/projects/{pid}/studies/{study['study_sha256']}/export", raw=True)
            pdf = download(page, '#export-pdf', 'initial')
            assert pdf.startswith(b'%PDF') and pdf == api(f"/projects/{pid}/studies/{study['study_sha256']}/pdf", raw=True)
            RECEIPT['checks'].append('Actual JSON/PDF browser downloads complete and equal retained API bytes')

            # A remote save must not replace a local edited draft after HTTP 409.
            project = current(page)
            remote = json.loads(project['snapshot_json'])
            remote['identity']['description'] = 'Remote fixture edit for conflict acceptance'
            api(f'/projects/{pid}/draft', 'PUT', {'expected_version': project['draft_version'], 'snapshot_json': json.dumps(remote)})
            page.get_by_text('Mass and payload placement', exact=True).click()
            mass = page.get_by_label('Mass, kg', exact=True).first
            old_mass = float(mass.input_value())
            mass.fill(str(old_mass+.25))
            page.locator('#save').click()
            page.locator('#draft-conflict').wait_for(state='visible')
            shot(page, '04-draft-conflict', '#draft-conflict')
            unsaved = json.loads(download(page, '#conflict-export', 'conflict'))
            assert unsaved['masses']['items'][0]['mass_kg'] == old_mass+.25
            page.locator('#conflict-keep').click()
            assert mass.input_value() == str(old_mass+.25)
            page.locator('#save').click()
            page.locator('#draft-conflict').wait_for(state='visible')
            click(page, '#conflict-reload')
            assert json.loads(page.locator('#snapshot').input_value())['masses']['items'][0]['mass_kg'] == old_mass
            RECEIPT['checks'].append('409 dialog preserves draft; unsaved export, keep, explicit replace verified')

            # Declared-mm analytic component, linked rotor and numeric round trip.
            page.get_by_text('Airframe geometry and rotor links', exact=True).click()
            stl = b'solid fixture\nfacet normal 0 0 1\nouter loop\nvertex -1000 -100 0\nvertex 1000 -100 0\nvertex 1000 100 0\nendloop\nendfacet\nfacet normal 0 0 1\nouter loop\nvertex -1000 -100 0\nvertex 1000 100 0\nvertex -1000 100 0\nendloop\nendfacet\nendsolid fixture\n'
            page.get_by_label('STL components', exact=True).set_input_files({'name':'analytic-airframe-mm.stl','mimeType':'application/octet-stream','buffer':stl})
            page.locator('label').filter(has_text='Source length units').locator('select').select_option('mm')
            page.get_by_role('button', name='Import and attach STL components', exact=True).click()
            page.locator('label').filter(has_text='Geometry reference for r0').locator('select').wait_for()
            select = page.locator('label').filter(has_text='Geometry reference for r0').locator('select')
            component = select.locator('option').nth(1).get_attribute('value')
            select.select_option(component)
            page.get_by_text('Rotors and retained performance sources', exact=True).click()
            page.get_by_label('Centre, m x', exact=True).first.fill('1.05')
            click(page, '#save')
            click(page, '#reload')
            snapshot = json.loads(page.locator('#snapshot').input_value())
            assert snapshot['rotors'][0]['center_body_m'][0] == 1.05 and snapshot['rotors'][0]['component_id'] == component
            digest = snapshot['assembly']['components'][0]['source_sha256']
            assert api('/projects/geometry-sources/'+digest, raw=True) == stl
            page.wait_for_function("document.querySelector('#layout-note').textContent.includes('1 retained airframe')")
            study = run(page)
            page.wait_for_function("document.querySelector('#layout-note').textContent.includes('Governing case:')")
            shot(page, '05-airframe-governing-case', '#layout-title + div')
            RECEIPT['checks'].append('Explicit mm import, original STL equality, rotor link/centre save/reopen, CG and governing case render')

            # Change the browser's native zoom through its settings UI API.
            settings = context.new_page()
            settings.goto('chrome://settings/appearance')
            zoom = settings.evaluate('async()=>{await chrome.settingsPrivate.setDefaultZoom(2);return await chrome.settingsPrivate.getDefaultZoom();}')
            assert zoom == 2
            page.wait_for_function('devicePixelRatio === 2')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
            page.locator('#study-report').scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            (EVIDENCE/'06-native-200-percent.png').write_bytes(base64.b64decode(cdp.send('Page.captureScreenshot', {'format':'png','fromSurface':False})['data']))
            RECEIPT['screenshots'].append('06-native-200-percent.png')
            zoom_dimensions = page.evaluate('({innerWidth,devicePixelRatio})')
            settings.evaluate('async()=>{await chrome.settingsPrivate.setDefaultZoom(1);}')
            settings.close()
            page.wait_for_function('devicePixelRatio === 1')
            RECEIPT['native_zoom'] = {'setting':zoom, **zoom_dimensions, 'method':'chrome.settingsPrivate native default browser zoom; no viewport override'}
            RECEIPT['checks'].append('Native Chromium browser zoom=2 verified by getDefaultZoom, DPR=2 and halved layout viewport; no document horizontal overflow')

            page.set_viewport_size({'width':390,'height':844})
            page.locator('#study-report').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
            table = page.locator('#study-report .table-scroll').first
            if table.count():
                table.focus()
                page.keyboard.press('ArrowRight')
                page.wait_for_function("document.querySelector('#study-report .table-scroll').scrollLeft > 0")
            shot(page, '07-mobile-capacity')
            assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
            RECEIPT['checks'].append('390px viewport without document overflow, reduced motion and keyboard table access')
            page.set_viewport_size({'width':1440,'height':1000})

            click(page, '#example')
            before = run(page)
            page.get_by_text('Mass and payload placement', exact=True).click()
            page.get_by_label('Candidate payload x, m', exact=True).fill('.8')
            click(page, '#save')
            after = run(page)
            page.locator('#compare-before').select_option(before['study_sha256'])
            page.locator('#compare-after').select_option(after['study_sha256'])
            click(page, '#compare')
            comparison = api(f"/projects/{current(page)['project_id']}/comparisons", 'POST', {'before': before['study_sha256'], 'after': after['study_sha256']})
            assert any(row['newly_active'] for row in comparison['constraint_changes'])
            assert [row['path'] for row in comparison['input_changes']] == ['/mission/payload_positions_body_m']
            shot(page, '08-comparison', '#comparison-report')
            RECEIPT['checks'].append('Retained before/after inputs and newly active constraints compared with non-causal qualification')

            # Make a rotor-map bound govern the layout, then show failure state.
            comparison_snapshot = json.loads(page.locator('#snapshot').input_value())
            comparison_snapshot['mission']['cases'] = [comparison_snapshot['mission']['cases'][0]]
            comparison_snapshot['assembly'] = snapshot['assembly']
            comparison_snapshot['rotors'][0]['component_id'] = component
            page.get_by_text('Design input JSON', exact=True).click()
            page.locator('#snapshot').fill(json.dumps(comparison_snapshot))
            click(page, '#save')
            run(page)
            page.wait_for_function("document.querySelector('#layout-note').textContent.includes('Amber active rotor limits:')")
            shot(page, '10-active-rotor-airframe', '#layout-title + div')
            click(page, '#motorout-example')
            motorout = run(page)
            assert motorout['outcome'] == 'feasible'
            failed_case = next(c for c in motorout['headline_candidate_checks'] if c['case_id'] == 'r0_failed')
            command = next(c for c in failed_case['candidate']['commands'] if c['rotor_id'] == 'r0')
            assert command['thrust_n'] == command['shaft_torque_nm'] == command['electrical_power_w'] == 0
            page.wait_for_function("document.querySelector('#layout-note').textContent.includes('Red failed rotors: r0')")
            shot(page, '11-motor-out-layout', '#layout-title + div')
            RECEIPT['checks'].append('Airframe preview highlights governing rotor map limits amber; octo failure preview highlights exactly zero-command r0 red')

            for index in range(2):
                started = time.perf_counter()
                click(page, '#realistic-example')
                run(page)
                download(page, '#export-study', f'rehearsal-{index+1}')
                download(page, '#export-pdf', f'rehearsal-{index+1}')
                RECEIPT['rehearsals_s'].append(round(time.perf_counter()-started,3))
            assert not errors, errors
            RECEIPT['checks'].append('Two timed automated realistic create/freeze/evaluate/export rehearsals, video recorded')
            RECEIPT['runtime_evidence'] = str(RUNTIME.relative_to(ROOT))
            RECEIPT['browser_version'] = context.browser.version
            cdp.send('Page.stopScreencast')
            context.close()
            assert len(frames) > 10
            concat = RUNTIME/'frames.txt'
            lines = []
            for index, (path, stamp) in enumerate(frames):
                lines.append(f"file '{path}'")
                duration = frames[index+1][1]-stamp if index+1 < len(frames) else 1.
                lines.append(f'duration {max(duration, .01)}')
            lines.append(f"file '{frames[-1][0]}'")
            concat.write_text('\n'.join(lines)+'\n')
            video = RUNTIME/'backup.webm'
            subprocess.run(['/usr/bin/ffmpeg', '-hide_banner', '-loglevel','error','-f','concat','-safe','0','-i',str(concat), '-vf','scale=1440:1000:force_original_aspect_ratio=decrease,pad=1440:1000:(ow-iw)/2:(oh-ih)/2','-c:v','libvpx-vp9','-threads','2','-b:v','1M','-y',str(video)], check=True)
            RECEIPT['recording'] = {'path':str(video.relative_to(ROOT)), 'frames':len(frames), 'bytes':video.stat().st_size, 'sha256':hashlib.sha256(video.read_bytes()).hexdigest(), 'method':'CDP screencast frame timestamps; system FFmpeg'}
        (EVIDENCE/'receipt.json').write_text(json.dumps(RECEIPT, indent=2)+'\n')
        print(json.dumps(RECEIPT, indent=2))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
