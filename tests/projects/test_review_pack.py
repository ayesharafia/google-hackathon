"""Synthetic archive/integrity/authorization checks, not physical validation."""
import hashlib
import io
import json
import zipfile

import pytest

from physimesh.projects import review_pack
from tests.projects.test_local_studies import AUTH, client
from tests.projects.test_reports import retained
from tests.projects.test_source_library import hosted  # noqa: F401


def unpack(response):
    assert response.status_code == 200, response.text[:500] if response.status_code != 200 else ''
    assert response.headers['content-type'] == 'application/zip'
    assert hashlib.sha256(response.content).hexdigest() == response.headers['X-Pack-SHA256']
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert names == sorted(set(names))
        assert all(not name.startswith('/') and '..' not in name.split('/') for name in names)
        assert len(names) <= 128 and sum(i.file_size for i in archive.infolist()) <= 40*1024*1024
        files = {name: archive.read(name) for name in names}
    hashes = json.loads(files['hashes.json'])
    assert set(hashes) == set(files)-{'hashes.json'}
    for name, entry in hashes.items():
        assert entry == {'sha256': hashlib.sha256(files[name]).hexdigest(), 'bytes': len(files[name])}
    return files


def test_exact_deterministic_pack_never_runs_solver_and_preserves_sources(tmp_path, monkeypatch):
    c = client(tmp_path)
    project, base, record = retained(c)
    route = base+'/studies/'+record['study_sha256']
    original = c.get(route+'/export', headers=AUTH).content
    def refuse(*args, **kwargs):
        pytest.fail('review package must not execute solver')
    monkeypatch.setattr('physimesh.projects.studies.capacity_from_snapshot', refuse)
    response = c.get(route+'/review-pack', headers=AUTH)
    files = unpack(response)
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['X-Study-SHA256'] == record['study_sha256']
    assert files['study.json'] == original
    assert files['snapshot.json'] == project['snapshot_json'].encode()
    assert files['report.pdf'] == c.get(route+'/pdf', headers=AUTH).content
    assert c.get(route+'/review-pack', headers=AUTH).content == response.content
    manifest = json.loads(files['manifest.json'])
    assert manifest['schema_version'] == 'study_review_pack_v1'
    assert manifest['snapshot_sha256'] == record['specification']['snapshot_sha256']
    assert manifest['snapshot_hash_scheme'] == 'si_numeric_snapshot_v1'
    assert manifest['snapshot_json_sha256'] == hashlib.sha256(files['snapshot.json']).hexdigest()
    assert response.headers['X-Project-ID'] == project['project_id']
    for digest in record['specification']['performance_source_sha256']:
        with c.app.state.projects.artifacts.open(digest) as stream:
            assert files['sources/'+digest+'.json'] == stream.read()
    assert b'original measurement spreadsheet' in files['README.txt']
    assert 'Original CSV/XLSX files and conversion manifests' in manifest['exclusions']
    assert json.loads(files['report-receipt.json'])['pdf_sha256'] == hashlib.sha256(files['report.pdf']).hexdigest()
    assert c.get(route+'/export', headers=AUTH).content == original
    assert c.get(route+'/review-pack').status_code == 401
    assert c.get('/api/drone/projects/other/studies/'+record['study_sha256']+'/review-pack', headers=AUTH).status_code == 404


def test_mutable_draft_does_not_change_review_package(tmp_path):
    c = client(tmp_path)
    project, base, record = retained(c)
    route = base+'/studies/'+record['study_sha256']+'/review-pack'
    first = c.get(route, headers=AUTH)
    draft = json.loads(project['snapshot_json'])
    draft['masses']['items'][0]['mass_kg'] += 1
    assert c.put(base+'/draft', headers=AUTH, json={'expected_version': 1, 'snapshot_json': json.dumps(draft)}).status_code == 200
    assert c.get(route, headers=AUTH).content == first.content


@pytest.mark.parametrize('action', ['corrupt', 'missing'])
def test_missing_or_corrupt_required_map_refuses_package_but_keeps_historical_json(tmp_path, action):
    c = client(tmp_path)
    _, base, record = retained(c)
    digest = record['specification']['performance_source_sha256'][0]
    path = c.app.state.artifact_backend._obj(digest)
    if action == 'corrupt':
        path.write_bytes(path.read_bytes()+b' ')
    else:
        path.unlink()
    route = base+'/studies/'+record['study_sha256']
    assert c.get(route+'/review-pack', headers=AUTH).status_code == 422
    assert c.get(route+'/export', headers=AUTH).status_code == 200


def test_corrupt_pdf_and_wrong_pdf_receipt_are_refused(tmp_path, monkeypatch):
    c = client(tmp_path)
    _, base, record = retained(c)
    route = base+'/studies/'+record['study_sha256']
    pdf = c.get(route+'/pdf', headers=AUTH)
    path = c.app.state.artifact_backend._obj(pdf.headers['X-PDF-SHA256'])
    original = path.read_bytes()
    path.write_bytes(original+b' ')
    assert c.get(route+'/review-pack', headers=AUTH).status_code == 422
    path.write_bytes(original)
    prepared = c.app.state.studies.pdf(base.split('/')[-1], record['study_sha256'])
    monkeypatch.setattr(c.app.state.studies, 'pdf', lambda *_: (prepared[0], {**prepared[1], 'pdf_sha256': '0'*64}))
    assert c.get(route+'/review-pack', headers=AUTH).status_code == 422


def test_conditioned_sources_include_exact_raw_dependencies(tmp_path):
    c = client(tmp_path)
    project = c.post('/api/drone/projects/examples/realistic', headers=AUTH).json()
    base = '/api/drone/projects/'+project['project_id']
    revision = c.post(base+'/revisions', headers=AUTH, json={'expected_version': project['draft_version']}).json()
    record = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': revision['revision_sha256']}).json()
    response = c.get(base+'/studies/'+record['study_sha256']+'/review-pack', headers=AUTH)
    files = unpack(response)
    links = json.loads(files['manifest.json'])['source_dependencies']
    assert any(link['raw_source_sha256'] for link in links)
    for link in links:
        for digest in filter(None, link.values()):
            with c.app.state.projects.artifacts.open(digest) as stream:
                assert files['sources/'+digest+'.json'] == stream.read()
    raw_digest = next(link['raw_source_sha256'] for link in links if link['raw_source_sha256'])
    c.app.state.artifact_backend._obj(raw_digest).unlink()
    assert c.get(base+'/studies/'+record['study_sha256']+'/review-pack', headers=AUTH).status_code == 422


@pytest.mark.parametrize('budget,value', [('MAX_MEMBERS', 7), ('MAX_BYTES', 100)])
def test_archive_budget_refuses_partial_output(tmp_path, monkeypatch, budget, value):
    c = client(tmp_path)
    _, base, record = retained(c)
    monkeypatch.setattr(review_pack, budget, value)
    response = c.get(base+'/studies/'+record['study_sha256']+'/review-pack', headers=AUTH)
    assert response.status_code == 422 and not response.content.startswith(b'PK')


def test_build_capacity_returns_retryable_refusal(tmp_path):
    c = client(tmp_path)
    _, base, record = retained(c)
    review_pack.BUILD_SLOTS.acquire()
    review_pack.BUILD_SLOTS.acquire()
    try:
        response = c.get(base+'/studies/'+record['study_sha256']+'/review-pack', headers=AUTH)
        assert response.status_code == 503 and response.headers['Retry-After'] == '2'
    finally:
        review_pack.BUILD_SLOTS.release()
        review_pack.BUILD_SLOTS.release()


def test_frozen_source_reference_mismatch_and_unsafe_digest_refused(tmp_path, monkeypatch):
    c = client(tmp_path)
    _, base, record = retained(c)
    studies = c.app.state.studies
    pid = base.split('/')[-1]
    raw, snapshot = studies.report_inputs(pid, record['study_sha256'])
    prepared = studies.pdf(pid, record['study_sha256'])
    for refs in [[], ['../escape'], record['specification']['performance_source_sha256']*2]:
        altered = json.loads(raw)
        altered['specification']['performance_source_sha256'] = refs
        from physimesh.projects.reports import report_identity
        changed = json.dumps(altered).encode()
        receipt = {**report_identity(changed, snapshot), 'pdf_sha256': hashlib.sha256(prepared[0]).hexdigest()}
        with monkeypatch.context() as patch:
            patch.setattr(studies, 'report_inputs', lambda *_, content=changed: (content, snapshot))
            with pytest.raises(ValueError, match='source bindings'):
                review_pack.build_review_pack(studies, pid, record['study_sha256'], (prepared[0], receipt))


def test_hosted_viewer_job_reuse_own_project_and_revoked_access(hosted, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from physimesh.platform.scoped_artifacts import artifact_scope
    from physimesh.platform.worker import run_one
    app, boss, viewer, _stranger, (a, *_), token, viewer_token, stranger_token = hosted
    c = TestClient(app)
    org = app.state.identity.authorize(boss, a)
    headers = {'Authorization': 'Bearer '+token, 'X-Organization-ID': org}
    project = c.post('/api/drone/projects/examples/hover', headers=headers).json()
    pid = project['project_id']
    invitation = app.state.identity.invite(boss, pid, viewer.email, 'viewer')['invitation_token']
    app.state.identity.accept(viewer, invitation)
    base = '/api/drone/projects/'+pid
    revision = c.post(base+'/revisions', headers=headers, json={'expected_version': 1}).json()
    with artifact_scope(pid):
        record = app.state.studies.run(pid, revision['revision_sha256'])
    route = base+'/studies/'+record['study_sha256']+'/review-pack'
    vh = {'Authorization': 'Bearer '+viewer_token}
    first = c.get(route, headers=vh)
    assert first.status_code == 202 and first.json()['kind'] == 'report'
    assert c.get(route, headers=vh).json()['job_id'] == first.json()['job_id']
    # macOS cannot run the Linux-only compute supervisor. Produce a real PDF
    # in a deterministic subprocess-output fixture; keep queue/fence/publication real.
    from pathlib import Path
    from types import SimpleNamespace

    from physimesh.projects.reports import render_pdf, report_identity
    with artifact_scope(pid):
        raw, snapshot = app.state.studies.report_inputs(pid, record['study_sha256'])
    pdf, receipt = render_pdf(raw, snapshot), report_identity(raw, snapshot)
    def compute(argv, **_kwargs):
        destination = Path(argv[-1])
        destination.write_text(json.dumps(receipt))
        destination.with_suffix('.pdf').write_bytes(pdf)
        return SimpleNamespace(pid=0, returncode=0, poll=lambda: 0, wait=lambda: 0)
    monkeypatch.setattr('physimesh.platform.worker.subprocess.Popen', compute)
    assert run_one(app, 'review-pack-fixture-worker', wall_s=30)
    assert app.state.jobs.get(pid, first.json()['job_id'])['state'] == 'succeeded'
    files = unpack(c.get(route, headers=vh))
    assert json.loads(files['manifest.json'])['project_id'] == pid
    assert c.get(route, headers={'Authorization': 'Bearer '+stranger_token}).status_code == 403
    assert c.get('/api/drone/projects/'+a+'/studies/'+record['study_sha256']+'/review-pack', headers=headers).status_code == 404
    # Knowing a retained digest is not entitlement to an ungranted artifact.
    digest = record['specification']['performance_source_sha256'][0]
    with app.state.metadata.connection(write=True) as db:
        db.execute('DELETE FROM artifact_access WHERE project_id=? AND digest=?', (pid, digest))
    assert c.get(route, headers=vh).status_code == 403
    assert c.get(base+'/studies/'+record['study_sha256']+'/export', headers=vh).status_code == 200
    app.state.identity.grant_artifact(pid, digest, len(app.state.artifact_backend._obj(digest).read_bytes()))
    assert c.get(route, headers=vh).status_code == 200
    app.state.identity.remove_member(boss, pid, viewer.user_id)
    assert c.get(route, headers=vh).status_code == 403
    assert c.get(route).status_code == 401


def test_diagnostic_study_package_preserves_unsupported_outcome_without_invented_sources(tmp_path):
    c = client(tmp_path)
    project = c.post('/api/drone/projects', headers=AUTH, json={'title': 'Synthetic missing inputs'}).json()
    base = '/api/drone/projects/'+project['project_id']
    frozen = c.post(base+'/revisions', headers=AUTH, json={'expected_version': 0}).json()
    record = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen['revision_sha256']}).json()
    files = unpack(c.get(base+'/studies/'+record['study_sha256']+'/review-pack', headers=AUTH))
    manifest = json.loads(files['manifest.json'])
    assert manifest['outcome'] == record['outcome'] == 'unsupported'
    assert json.loads(files['study.json'])['payload_lower_bound_kg'] is None
    assert manifest['source_dependencies'] == []
    assert not any(name.startswith('sources/') for name in files)
