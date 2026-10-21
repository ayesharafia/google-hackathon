"""Real publication/ledger path; deterministic subprocess output isolates storage faults."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.provenance import canonical_json
from physimesh.platform.identity import Denied, Principal
from physimesh.platform.scoped_artifacts import artifact_scope
from physimesh.platform.worker import run_one
from physimesh.projects.reports import render_pdf, report_identity


@pytest.fixture(params=['study', 'report'])
def publication(tmp_path, monkeypatch, request):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', '', None, hosted_mode=True))
    identity = app.state.identity
    uid = identity.provision('worker@example.test', password='worker-fixture-password')
    principal = Principal(uid, 'worker@example.test')
    org = identity.organization(uid, 'Worker accounting fixture')
    project = app.state.projects.create('Incomplete synthetic worker fixture')
    pid = project['project_id']
    identity.claim_project(principal, org, pid)
    with artifact_scope(pid):
        frozen = app.state.projects.freeze(pid, project['draft_version'], 'screening')
        result = app.state.studies.evaluate(pid, frozen['revision_sha256'])
        raw = canonical_json(result).encode()
        spec = {'revision_sha256': frozen['revision_sha256'],
                'application_build': app.state.build.get('build_sha256')}
        receipt = None
        if request.param == 'report':
            app.state.studies.run(pid, frozen['revision_sha256'])
            study_raw, snapshot = app.state.studies.report_inputs(pid, result['study_sha256'])
            receipt = report_identity(study_raw, snapshot)
            raw = render_pdf(study_raw, snapshot)
            spec.update(study_sha256=result['study_sha256'], report_identity=receipt)
    job = app.state.jobs.submit(pid, request.param, spec)

    def compute(argv, **kwargs):
        output = Path(argv[-1])
        if request.param == 'study':
            output.write_bytes(raw)
        else:
            output.write_text(json.dumps(receipt))
            output.with_suffix('.pdf').write_bytes(raw)
        return SimpleNamespace(pid=0, returncode=0, poll=lambda: 0, wait=lambda: 0)

    monkeypatch.setattr('physimesh.platform.worker.subprocess.Popen', compute)
    fixture = SimpleNamespace(app=app, pid=pid, job=job, kind=request.param, raw=raw,
                              digest=hashlib.sha256(raw).hexdigest(), study=result['study_sha256'], receipt=receipt)
    fixture.before = accounting(fixture)
    try:
        yield fixture
    finally:
        app.state.metadata.close()


def accounting(fixture):
    with fixture.app.state.metadata.connection() as db:
        return (db.execute('SELECT artifact_bytes FROM platform_quota').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM artifact_access').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM artifact_reservations').fetchone()[0])


def job(fixture):
    return fixture.app.state.jobs.get(fixture.pid, fixture.job['job_id'])


def assert_unaccepted(fixture):
    assert job(fixture)['result_json'] is None
    if fixture.kind == 'study':
        assert fixture.app.state.projects.repository.get(fixture.pid)['studies'] == []
    else:
        with artifact_scope(fixture.pid):
            assert fixture.app.state.studies.cached_pdf(fixture.pid, fixture.study) is None


def test_worker_charges_actual_persisted_output_then_accepts_association(publication):
    fixture = publication
    assert run_one(fixture.app, 'accounted-worker')
    retained = job(fixture)
    assert retained['state'] == 'succeeded'
    assert json.loads(retained['result_json'])['artifact_sha256'] == fixture.digest
    added_bytes, added_objects = len(fixture.raw), 1
    if fixture.kind == 'report':
        # Successful materialization also retains the verified report receipt.
        added_bytes += len(canonical_json({**fixture.receipt, 'pdf_sha256': fixture.digest}).encode())
        added_objects += 1
    assert accounting(fixture) == (fixture.before[0]+added_bytes, fixture.before[1]+added_objects, 0)
    with artifact_scope(fixture.pid):
        if fixture.kind == 'study':
            assert fixture.app.state.studies.export(fixture.pid, fixture.study) == fixture.raw
        else:
            assert fixture.app.state.studies.cached_pdf(fixture.pid, fixture.study)[0] == fixture.raw


def test_worker_quota_refusal_precedes_backend_write(publication, monkeypatch):
    fixture = publication
    with fixture.app.state.metadata.connection(write=True) as db:
        db.execute('UPDATE platform_quota SET artifact_bytes=50000000000')

    def unexpected(*args, **kwargs):
        pytest.fail('over-budget worker reached artifact persistence')

    monkeypatch.setattr(fixture.app.state.artifact_backend, 'put_bytes', unexpected)
    assert run_one(fixture.app, 'quota-refused-worker')
    assert job(fixture)['state'] == 'failed'
    assert 'artifact budget exceeded' in job(fixture)['reason']
    assert_unaccepted(fixture)
    assert accounting(fixture) == (50_000_000_000, fixture.before[1], 0)


@pytest.mark.parametrize('failure', ['io', 'wrong_digest', 'corrupt_existing'])
def test_worker_storage_failure_grants_no_output_access_or_acceptance(publication, monkeypatch, failure):
    fixture = publication
    backend = fixture.app.state.artifact_backend
    if failure == 'corrupt_existing':
        path = backend._obj(fixture.digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'corrupt worker evidence')
    else:
        def fail(*args, **kwargs):
            if failure == 'io':
                raise OSError('synthetic worker storage failure')
            return 'f'*64
        monkeypatch.setattr(backend, 'put_bytes', fail)
    assert run_one(fixture.app, 'failed-publication-worker')
    assert job(fixture)['state'] == ('queued' if failure == 'io' else 'failed')
    assert_unaccepted(fixture)
    assert accounting(fixture) == fixture.before
    with pytest.raises(Denied):
        fixture.app.state.identity.require_artifact(fixture.pid, fixture.digest)


def test_cancellation_during_storage_keeps_fence_and_accounts_unaccepted_bytes(publication, monkeypatch):
    fixture = publication
    backend = fixture.app.state.artifact_backend
    original = backend.put_bytes

    def cancel_after_write(*args, **kwargs):
        digest = original(*args, **kwargs)
        fixture.app.state.jobs.cancel(fixture.pid, fixture.job['job_id'])
        return digest

    monkeypatch.setattr(backend, 'put_bytes', cancel_after_write)
    assert run_one(fixture.app, 'cancelled-publication-worker')
    assert job(fixture)['state'] == 'cancelled'
    assert_unaccepted(fixture)
    assert accounting(fixture) == (fixture.before[0]+len(fixture.raw), fixture.before[1]+1, 0)
    # Storage accounting is distinct from accepted engineering evidence. No GC is implied.
    fixture.app.state.identity.require_artifact(fixture.pid, fixture.digest)
