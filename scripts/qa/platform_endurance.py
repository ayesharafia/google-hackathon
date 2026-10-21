#!/usr/bin/env python3
"""Bounded synthetic hosted journey soak; the requested 24-hour target remains distinct."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from benchmark_baseline import dump, proc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=300)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='physimesh-soak-') as directory:
        root = Path(directory)
        env = {**os.environ, 'PHYSIMESH_MODE': 'hosted', 'PHYSIMESH_DATA_ROOT': str(root),
               'PHYSIMESH_DB_PATH': str(root/'jobs.sqlite')}
        from physimesh.api.app import create_app
        from physimesh.api.settings import Settings
        bootstrap = create_app(Settings(root, root/'jobs.sqlite', '', None, hosted_mode=True))
        password = secrets.token_urlsafe(24)
        uid = bootstrap.state.identity.provision('soak@example.test', password=password)
        org = bootstrap.state.identity.organization(uid, 'Synthetic bounded soak')
        bootstrap.state.metadata.close()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        commands = [[sys.executable, '-m', 'uvicorn', 'physimesh.api.app:app_from_environment', '--factory',
                     '--host', '127.0.0.1', '--port', str(port)],
                    [sys.executable, '-m', 'physimesh.platform.worker']]
        with (root/'processes.log').open('w') as log:
            processes = [subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                         for command in commands]
            try:
                client = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=60, trust_env=False)
                for _ in range(200):
                    try:
                        if client.get('/api/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.05)
                else:
                    raise RuntimeError('soak API failed readiness')
                login = client.post('/api/drone/platform/login', json={'email': 'soak@example.test', 'password': password})
                login.raise_for_status()
                client.headers.update({'Authorization': 'Bearer '+login.json()['token'], 'X-Organization-ID': org})
                def request(method, path, **kw):
                    response = client.request(method, path, **kw)
                    response.raise_for_status()
                    return response
                project = request('POST', '/api/drone/projects/examples/realistic').json()
                base = '/api/drone/projects/'+project['project_id']
                snapshot, version = json.loads(project['snapshot_json']), project['draft_version']
                samples, completed, start = [], 0, time.monotonic()
                def sample():
                    samples.append({'t_s': time.monotonic()-start, 'api': proc(processes[0].pid),
                                    'worker_supervisor': proc(processes[1].pid),
                                    'data_bytes': sum(p.stat().st_size for p in root.rglob('*') if p.is_file())})
                def wait(job):
                    deadline = time.monotonic()+130
                    while time.monotonic() < deadline:
                        value = request('GET', base+'/jobs/'+job['job_id']).json()
                        if value['state'] == 'succeeded':
                            return json.loads(value['result_json'])
                        assert value['state'] not in ('failed', 'cancelled'), value['reason']
                        sample(); time.sleep(.25)
                    raise AssertionError('soak job failed to finish')
                while time.monotonic()-start < args.seconds:
                    snapshot['identity']['description'] = f'Synthetic soak revision {completed}'
                    saved = request('PUT', base+'/draft', json={'expected_version': version,
                        'snapshot_json': json.dumps(snapshot)}).json()
                    version = saved['draft_version']
                    revision = request('POST', base+'/revisions', json={'expected_version': version}).json()
                    accepted = wait(request('POST', base+'/studies', json={
                        'revision_sha256': revision['revision_sha256']}).json())
                    path = base+'/studies/'+accepted['study_sha256']
                    study = request('GET', path).json()
                    assert study['outcome'] == 'feasible'
                    assert abs(study['payload_lower_bound_kg']-4.2531506527296115) < 1e-7
                    first = request('GET', path+'/pdf')
                    assert first.status_code == 202
                    wait(first.json())
                    pdf = request('GET', path+'/pdf').content
                    assert pdf.startswith(b'%PDF-') and request('GET', path+'/pdf').content == pdf
                    request('GET', '/api/drone/projects')
                    request('GET', base+'/history/studies')
                    sample(); completed += 1
                jobs = request('GET', base+'/jobs', params={'limit': 100}).json()['jobs']
                assert all(j['state'] == 'succeeded' for j in jobs)
                receipt = {'fixture': 'analytic V4', 'configured_seconds': args.seconds,
                    'elapsed_s': time.monotonic()-start, 'complete_study_and_pdf_journeys': completed,
                    'failures': 0, 'lost_accepted_jobs': 0, 'samples': samples,
                    'qualification': 'Single-client bounded SQLite hosted journey; not the 24-hour target or hosted SLO.'}
                dump(args.receipt, receipt)
                print(json.dumps({key: value for key, value in receipt.items() if key != 'samples'}))
                client.close()
            finally:
                for process in processes:
                    process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()


if __name__ == '__main__':
    main()
