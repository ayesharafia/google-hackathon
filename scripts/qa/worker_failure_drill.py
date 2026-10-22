#!/usr/bin/env python3
"""Actual supervisor SIGKILL, child death, accelerated lease expiry and restart drill."""
import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.jobs import StaleAttempt
from physimesh.platform.worker import accept_publication, run_one


def compute_child_stopped(pid):
    """A missing proc entry or a zombie confirms the child has stopped."""
    try:
        status = Path(f'/proc/{pid}/stat').read_text()
    except (FileNotFoundError, ProcessLookupError):
        # procfs can disappear during open/read as the child exits.
        return True
    return status.rsplit(')', 1)[1].strip().startswith('Z')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='physimesh-worker-drill-') as directory:
        root = Path(directory)
        env = {**os.environ, 'PHYSIMESH_MODE': 'hosted', 'PHYSIMESH_DATA_ROOT': str(root),
               'PHYSIMESH_DB_PATH': str(root/'jobs.sqlite')}
        os.environ.update(PHYSIMESH_MODE='hosted', PHYSIMESH_DATA_ROOT=str(root), PHYSIMESH_DB_PATH=str(root/'jobs.sqlite'))
        app = create_app(Settings(root, root/'jobs.sqlite', '', None, hosted_mode=True))
        password = secrets.token_urlsafe(24)
        uid = app.state.identity.provision('owner@example.test', password=password)
        org = app.state.identity.organization(uid, 'Synthetic failure drill')
        client = TestClient(app)
        token = client.post('/api/drone/platform/login', json={'email': 'owner@example.test', 'password': password}).json()['token']
        headers = {'Authorization': 'Bearer '+token, 'X-Organization-ID': org}
        project = client.post('/api/drone/projects/examples/realistic', headers=headers).json()
        base = '/api/drone/projects/'+project['project_id']
        revision = client.post(base+'/revisions', headers=headers, json={'expected_version': project['draft_version']}).json()
        job = client.post(base+'/studies', headers=headers, json={'revision_sha256': revision['revision_sha256']}).json()
        with (root/'supervisor.log').open('w') as log:
            supervisor = subprocess.Popen([sys.executable, '-m', 'physimesh.platform.worker', '--once'], env=env,
                                          stdout=log, stderr=subprocess.STDOUT)
            child, stale = None, None
            try:
                deadline = time.monotonic()+20
                while time.monotonic() < deadline:
                    pids = list((root/'attempts').glob('*/compute.pid')) if (root/'attempts').exists() else []
                    children = [p.read_text() for p in pids]
                    inputs = list((root/'attempts').glob('*/input.json')) if (root/'attempts').exists() else []
                    if children and inputs:
                        child, stale = int(children[0]), json.loads(inputs[0].read_text())
                        time.sleep(.3)
                        break
                    if supervisor.poll() is not None:
                        current = app.state.jobs.get(project['project_id'], job['job_id'])
                        raise RuntimeError('supervisor exited before interrupt; state='+current['state']+
                            '; attempts='+str(len(current['attempts']))+'; build='+str(current['build_sha256'])+
                            '; attempts-root='+str((root/'attempts').exists())+
                            '; files='+str([str(p.relative_to(root)) for p in root.glob('attempts/**/*')])+
                            '; log='+(root/'supervisor.log').read_text()[-2000:])
                    time.sleep(.02)
                assert child and stale, 'isolated child not observed'
                os.kill(supervisor.pid, signal.SIGKILL)
                supervisor.wait(timeout=10)
                for _ in range(100):
                    if compute_child_stopped(child):
                        break
                    time.sleep(.02)
                else:
                    raise AssertionError('orphan compute child survived supervisor death')
                interrupted = app.state.jobs.get(project['project_id'], job['job_id'])
                assert interrupted['state'] == 'running' and interrupted['result_json'] is None
                # Accelerate ONLY the retained lease timestamp, not model/worker code.
                with app.state.metadata.connection(write=True) as db:
                    db.execute('UPDATE durable_jobs SET lease_until=0 WHERE job_id=?', (job['job_id'],))
                assert run_one(app, 'replacement-worker')
                accepted = app.state.jobs.get(project['project_id'], job['job_id'])
                assert accepted['state'] == 'succeeded'
                assert [attempt['state'] for attempt in accepted['attempts']] == ['expired', 'accepted']
                try:
                    app.state.jobs.complete(stale, {'artifact_sha256': '0'*64})
                except StaleAttempt:
                    pass
                else:
                    raise AssertionError('stale generation published')
                original = accepted['result_json']
                # Re-materialization is idempotent, including after reopening the application.
                reopened = create_app(Settings(root, root/'jobs.sqlite', '', None, hosted_mode=True))
                accept_publication(reopened, accepted)
                accept_publication(reopened, accepted)
                assert reopened.state.jobs.get(project['project_id'], job['job_id'])['result_json'] == original
                reopened.state.metadata.close()
                # A real subprocess with an intentionally tiny wall budget fails without publication.
                receipt = json.loads(original)
                pdf = client.get(base+'/studies/'+receipt['study_sha256']+'/pdf', headers=headers).json()
                assert run_one(app, 'budget-worker', wall_s=.01)
                limited = app.state.jobs.get(project['project_id'], pdf['job_id'])
                assert limited['state'] == 'failed' and limited['result_json'] is None
                evidence = {'fixture': 'analytic V4', 'supervisor_sigkill': 'passed', 'compute_child_death': 'passed',
                    'lease_expiry': 'accelerated database timestamp, not a real 30-second delay',
                    'restart_acceptance': 'passed', 'stale_publication_denied': 'passed',
                    'accepted_receipt_reopened_materialization': 'passed', 'wall_budget_denied_publication': 'passed',
                    'accepted_resources': receipt['resources']}
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                args.receipt.write_text(json.dumps(evidence, indent=2)+'\n')
                print(json.dumps(evidence))
            finally:
                if supervisor.poll() is None:
                    supervisor.kill(); supervisor.wait()
                app.state.metadata.close()


if __name__ == '__main__':
    main()
