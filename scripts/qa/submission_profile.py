"""Bounded hosted SQLite submission diagnostics; never a network or provider SLO.

Run from a source checkout with its development dependencies installed:
  python scripts/qa/submission_profile.py --output .backend/submission-profile-new
Only disposable synthetic inputs are used; no worker/solver is started. Output is
allowlisted and contains no credentials, response bodies, or design input values.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.metadata
import json
import secrets
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def stage_spans(targets, observations):
    """Temporarily wrap instance methods; retain durations only, including failures.

    Spans are inclusive, potentially nested, and must never be summed as a
    partition of request time. The caller runs requests serially.
    """
    restored = []
    try:
        for instance, method, label in targets:
            original = getattr(instance, method)
            own = method in instance.__dict__
            previous = instance.__dict__.get(method)

            def wrap(action, name):
                @functools.wraps(action)
                def measured(*args, **kwargs):
                    started = time.perf_counter()
                    ok = False
                    try:
                        result = action(*args, **kwargs)
                        ok = True
                        return result
                    finally:
                        observations.append({'stage': name,
                                             'elapsed_ms': (time.perf_counter()-started)*1000,
                                             'returned': ok})
                return measured

            restored.append((instance, method, own, previous))
            setattr(instance, method, wrap(original, label))
        yield
    finally:
        for instance, method, own, previous in reversed(restored):
            if own:
                setattr(instance, method, previous)
            else:
                delattr(instance, method)


def observe_submission(client, path, revision):
    """Measure request through complete buffered response without logging its body."""
    started = time.perf_counter()
    status, size, job, queued, error = 0, 0, None, False, None
    try:
        response = client.post(path+'/studies', json={'revision_sha256': revision})
        status, size = response.status_code, len(response.content)
        if status == 202:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get('job_id'), str):
                job = body['job_id']
                queued = body.get('state') == 'queued'
                if not queued:
                    error = 'unexpected_job_state'
            else:
                error = 'invalid_acceptance_body'
    except Exception:  # noqa: BLE001 - retain failure without exposing exception data
        # Never serialize exception messages: they can contain paths, SQL or tokens.
        error = 'request_exception'
    elapsed = (time.perf_counter()-started)*1000
    observation = {'status': status, 'response_bytes': size, 'full_body_latency_ms': elapsed,
                   'accepted_queued': status == 202 and queued, 'error': error}
    return observation, job


def cancel_observation(client, path, job):
    try:
        response = client.post(path+'/jobs/'+job+'/cancel')
        if response.status_code != 200:
            return {'cancelled': False, 'cancellation_error': 'non_200_cancellation'}
        body = response.json()
        ok = isinstance(body, dict) and body.get('state') == 'cancelled'
        return {'cancelled': ok, 'cancellation_error': None if ok else 'invalid_cancellation_body'}
    except Exception:  # noqa: BLE001 - retain failure without exposing exception data
        return {'cancelled': False, 'cancellation_error': 'cancellation_exception'}


def source_identity(root):
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((root/'src').rglob('*'))
              if p.is_file() and p.suffix in ('.py', '.json', '.yaml', '.yml')}
    if not hashes:
        raise ValueError('run from a source checkout containing src')
    return {'source_sha256': hashes,
            'source_manifest_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def run(root, repeats):
    if not 1 <= repeats <= 20:
        raise ValueError('repeats must be between 1 and 20')
    sys.path.insert(0, str(root/'src'))
    from fastapi.testclient import TestClient

    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings

    report = {'schema_version': 'submission_diagnostics_v1', 'utc': datetime.now(UTC).isoformat(),
              **source_identity(root), 'python': sys.version,
              'workload': 'realistic analytic fixture, fresh frozen revision for every observation',
              'environment': 'hosted mode; disposable SQLite/local artifacts; serial in-process TestClient',
              'timing': 'perf_counter request start through full buffered response body; setup/cancel excluded',
              'qualification': 'Diagnostic only; no worker/physics execution, concurrency, network or PostgreSQL measurement. '
                               'Spans are inclusive, may nest and are not additive. Instrumented timings are separate '
                               'from primary timings. Small sample maxima are not SLO tail estimates.',
              'repeats': repeats, 'observations': [],
              'dependencies': {name: importlib.metadata.version(name) for name in
                               ('fastapi', 'httpx', 'starlette', 'pydantic', 'numpy', 'scipy')}}
    with tempfile.TemporaryDirectory(prefix='physicore-submission-') as directory:
        data = Path(directory)
        app = create_app(Settings(data, data/'jobs.sqlite', '', None, hosted_mode=True))
        report['application_build_sha256'] = app.state.build.get('build_sha256')
        report['model_identity'] = app.state.studies.model_identity
        report['build_qualification'] = 'Source checkout; source/dependency receipts retained; not a packaged release.'
        identity = app.state.identity
        password = secrets.token_urlsafe(24)
        email = 'submission-diagnostic@example.test'
        user = identity.provision(email, password=password)
        org = identity.organization(user, 'Disposable submission diagnostics')
        with TestClient(app, raise_server_exceptions=False) as client:
            login = client.post('/api/drone/platform/login', json={'email': email, 'password': password})
            login.raise_for_status()
            client.headers.update({'Authorization': 'Bearer '+login.json()['token'], 'X-Organization-ID': org})
            targets = [(identity, 'session', 'identity.session'),
                       (identity, 'authorize', 'identity.authorize'),
                       (app.state.projects.repository, 'revision', 'repository.revision'),
                       (app.state.jobs, 'submit', 'jobs.submit')]
            for repeat in range(1, repeats+1):
                # Alternate order; do not time repeated admission of an existing job.
                phases = ('primary', 'diagnostic') if repeat % 2 else ('diagnostic', 'primary')
                for phase in phases:
                    project_response = client.post('/api/drone/projects/examples/realistic')
                    project_response.raise_for_status()
                    project = project_response.json()
                    path = '/api/drone/projects/'+project['project_id']
                    frozen = client.post(path+'/revisions', json={'expected_version': project['draft_version']})
                    frozen.raise_for_status()
                    revision = frozen.json()['revision_sha256']
                    spans = []
                    if phase == 'diagnostic':
                        with stage_spans(targets, spans):
                            measured, job = observe_submission(client, path, revision)
                    else:
                        measured, job = observe_submission(client, path, revision)
                    measured.update(repeat=repeat, phase=phase, stage_spans=spans,
                                    snapshot_sha256=hashlib.sha256(project['snapshot_json'].encode()).hexdigest(),
                                    revision_sha256=revision)
                    if job:
                        measured.update(cancel_observation(client, path, job))
                    else:
                        measured.update(cancelled=False, cancellation_error='no_accepted_job')
                    report['observations'].append(measured)
    report['all_accepted_and_cancelled'] = all(o['accepted_queued'] and o['cancelled'] for o in report['observations'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory; refusing overwrite')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error('repeats must be between 1 and 20')
    args.output.mkdir(parents=True, exist_ok=False)
    report = run(ROOT, args.repeats)
    (args.output/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print('Submission diagnostics: '+('all accepted/cancelled' if report['all_accepted_and_cancelled'] else 'failures retained'))
    return 0 if report['all_accepted_and_cancelled'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
