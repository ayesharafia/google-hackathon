#!/usr/bin/env python3
"""Verify an installed wheel's resources and complete V4 journey outside its checkout."""
import argparse
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    args = parser.parse_args()
    python = args.python.resolve()
    with tempfile.TemporaryDirectory(prefix='physimesh-wheel-') as directory:
        root = Path(directory)
        identity = subprocess.run([str(python), '-c',
            'import json; from physimesh.platform.release import build_identity; print(json.dumps(build_identity()))'],
            cwd=root, capture_output=True, text=True, check=True)
        build = json.loads(identity.stdout)
        assert build.get('build_sha256') and not build.get('dirty'), 'requires a clean release wheel'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        token = secrets.token_urlsafe(32)
        env = {**os.environ, 'PHYSIMESH_MODE': 'local', 'PHYSIMESH_API_TOKEN': token,
               'PHYSIMESH_DATA_ROOT': str(root/'data'), 'PHYSIMESH_DB_PATH': str(root/'data/jobs.sqlite'),
               'MPLCONFIGDIR': str(root/'cache'), 'XDG_CACHE_HOME': str(root/'cache')}
        env.pop('PYTHONPATH', None)
        base = f'http://127.0.0.1:{port}'
        def request(path, method='GET', body=None):
            req = urllib.request.Request(base+path, method=method,
                headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'},
                data=None if body is None else json.dumps(body).encode())
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read()
                return raw if not response.headers.get('Content-Type', '').startswith('application/json') else json.loads(raw)
        with (root/'api.log').open('w') as log:
            server = subprocess.Popen([str(python), '-m', 'uvicorn', 'physimesh.api.app:app_from_environment',
                '--factory', '--host', '127.0.0.1', '--port', str(port)], cwd=root, env=env,
                stdout=log, stderr=subprocess.STDOUT)
            started = time.monotonic()
            try:
                for _ in range(200):
                    if server.poll() is not None:
                        raise RuntimeError('installed wheel server exited')
                    try:
                        if request('/api/health')['status'] == 'ok':
                            break
                    except OSError:
                        pass
                    time.sleep(.05)
                else:
                    raise RuntimeError('installed wheel startup timed out')
                startup = time.monotonic()-started
                assert b'id="projects"' in request('/web/workbench.html')
                assert b'freeze' in request('/web/js/workbench.js')
                project = request('/api/drone/projects/examples/realistic', 'POST')
                path = '/api/drone/projects/'+project['project_id']
                revision = request(path+'/revisions', 'POST', {'expected_version': project['draft_version']})
                study = request(path+'/studies', 'POST', {'revision_sha256': revision['revision_sha256']})
                assert study['schema_version'] == 'local_mission_capacity_v4' and study['outcome'] == 'feasible'
                assert abs(study['payload_lower_bound_kg']-4.2531506527296115) < 1e-7
                pdf_path = path+'/studies/'+study['study_sha256']+'/pdf'
                pdf = request(pdf_path)
                assert pdf.startswith(b'%PDF-') and request(pdf_path) == pdf
                print(json.dumps({'journey': 'passed outside checkout', 'build_sha256': build['build_sha256'],
                                  'revision': build['revision'], 'startup_s': startup,
                                  'pdf_sha256': hashlib.sha256(pdf).hexdigest(), 'resource_files': len(build['resources'])}))
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill(); server.wait()


if __name__ == '__main__':
    main()
