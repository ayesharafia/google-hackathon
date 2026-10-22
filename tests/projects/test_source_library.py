"""Authorized immutable source reuse, with synthetic measurements only."""
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.identity import Denied
from physimesh.platform.scoped_artifacts import artifact_scope
from physimesh.projects.repository import ProjectMissing
from physimesh.projects.source_library import SourceLibrary
from physimesh.projects.tabular import ImportSelection

RAW = b'rpm,force,torque,power\r\n1000,1,0,10\r\n2000,2,0,20\r\n'
SPEC = {'start_row': 2, 'end_row': 3,
        'columns': {'rpm': 1, 'thrust_n': 2, 'shaft_torque_nm': 3, 'power_w': 4},
        'units': {'rpm': 'rpm', 'thrust_n': 'N', 'shaft_torque_nm': 'Nm', 'power_w': 'W'},
        'declarations': {'dataset_id': 'synthetic-import', 'configuration_id': 'fixture-rotor',
                         'source_kind': 'analytic_fixture', 'source_description': 'Synthetic tests only',
                         'torque_convention': 'absorbed_shaft_magnitude', 'density_kg_m3': 1.225,
                         'axial_inflow_m_s': 0.0, 'pitch_deg': 0.0, 'max_continuous_duration_s': 600.0,
                         'power_basis': 'electrical', 'covered_intervals_rpm': [[1000.0, 2000.0]]}}
AUTH = {'Authorization': 'Bearer test-token'}


@pytest.fixture
def local(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'test-token', None))
    client = TestClient(app)
    a = client.post('/api/drone/projects', headers=AUTH, json={'title': 'Synthetic source owner'}).json()['project_id']
    b = client.post('/api/drone/projects', headers=AUTH, json={'title': 'Synthetic reuse target'}).json()['project_id']
    return client, a, b


def post(client, project, action, *, raw=RAW, spec=SPEC, name='measurements.csv', headers=AUTH):
    return client.post(f'/api/drone/projects/{project}/source-library/{action}', headers=headers,
                       data={'spec': json.dumps(spec)}, files={'file': (name, raw)})


def test_preview_has_no_retained_objects_and_save_preserves_original_bytes(local):
    client, a, _ = local
    before = list(client.app.state.artifact_backend.root.glob('objects/*/*'))
    preview = post(client, a, 'preview')
    assert preview.status_code == 200 and preview.json()['valid'], preview.text
    assert list(client.app.state.artifact_backend.root.glob('objects/*/*')) == before
    saved = post(client, a, 'save')
    assert saved.status_code == 201, saved.text
    receipt = saved.json()
    assert receipt['manifest']['file_sha256'] == hashlib.sha256(RAW).hexdigest()
    assert receipt['source_sha256'] != receipt['manifest']['file_sha256']
    digest = receipt['entry']['entry_id']
    response = client.get(f'/api/drone/projects/{a}/source-library/{digest}/original', headers=AUTH)
    assert response.content == RAW and response.headers['cache-control'] == 'private, no-store'
    assert client.get(f'/api/drone/projects/{a}', headers=AUTH).json()['draft_version'] == 0


def test_restart_idempotency_search_pagination_and_cross_project_reuse(local):
    client, a, b = local
    first = post(client, a, 'save').json()
    assert post(client, a, 'save').json() == first
    restarted = TestClient(create_app(client.app.state.settings))
    page = restarted.get(f'/api/drone/projects/{b}/source-library?query=synthetic', headers=AUTH).json()
    assert len(page['entries']) == 1
    copied = restarted.post(f'/api/drone/projects/{b}/source-library/{first["entry"]["entry_id"]}/reuse', headers=AUTH)
    assert copied.status_code == 200, copied.text
    assert copied.json()['source_sha256'] == first['source_sha256']
    assert copied.json()['entry']['project_id'] == b
    assert len(restarted.get(f'/api/drone/projects/{b}/source-library?limit=1', headers=AUTH).json()['entries']) == 1
    page1 = restarted.get(f'/api/drone/projects/{b}/source-library?limit=1', headers=AUTH).json()
    assert page1['next_cursor']
    page2 = restarted.get(f'/api/drone/projects/{b}/source-library?after={page1["next_cursor"]}', headers=AUTH).json()
    assert len(page2['entries']) == 1
    assert page1['entries'][0]['entry_id'] != page2['entries'][0]['entry_id']
    assert restarted.get(f'/api/drone/projects/{b}/source-library?query=%25', headers=AUTH).json()['entries'] == []


def test_corrupt_original_and_failed_storage_never_return_completed_entries(local, monkeypatch):
    client, a, b = local
    receipt = post(client, a, 'save').json()
    path = client.app.state.artifact_backend._obj(receipt['manifest']['file_sha256'])
    path.write_bytes(b'corrupted')
    assert client.get(f'/api/drone/projects/{b}/source-library/{receipt["entry"]["entry_id"]}', headers=AUTH).status_code == 422
    def failed(*args, **kwargs):
        raise ValueError('synthetic storage failure')
    monkeypatch.setattr(client.app.state.projects.artifacts, 'put_bytes', failed)
    assert post(client, b, 'save').status_code == 422
    with client.app.state.metadata.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM source_library WHERE project_id=?', (b,)).fetchone()[0] == 0


def test_concurrent_save_is_idempotent(local):
    client, a, _ = local
    library = client.app.state.source_library
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: library.save(a, RAW, 'test.csv', ImportSelection.model_validate(SPEC)), range(8)))
    assert len({result['entry']['entry_id'] for result in results}) == 1


def test_invalid_rows_missing_auth_size_and_xlsx_api(local):
    client, a, _ = local
    assert post(client, a, 'preview', raw=RAW.replace(b',1,', b',=1+1,')).json()['valid'] is False
    assert post(client, a, 'save', raw=RAW.replace(b',1,', b',=1+1,')).status_code == 422
    assert post(client, a, 'inspect', spec={}, headers={}).status_code == 401
    assert post(client, a, 'preview', spec={**SPEC, 'columns': {}}).status_code == 422
    assert post(client, a, 'inspect', spec={}, raw=b'x' * (2*1024*1024+1)).status_code == 422
    workbook = Workbook()
    for row in [['r', 'f', 'q', 'p'], [1000, 1, 0, 10], [2000, 2, 0, 20]]:
        workbook.active.append(row)
    output = io.BytesIO()
    workbook.save(output)
    assert post(client, a, 'inspect', name='test.xlsx', raw=output.getvalue(), spec={}).json()['needs_sheet']
    assert post(client, a, 'save', name='test.xlsx', raw=output.getvalue(), spec={**SPEC, 'sheet': 'Sheet'}).status_code == 201


@pytest.fixture
def hosted(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', '', None, hosted_mode=True))
    identity = app.state.identity
    owner = identity.provision('owner@example.test', password='synthetic-password')
    identity.provision('member@example.test', password='synthetic-password')
    outsider = identity.provision('outsider@example.test', password='synthetic-password')
    def principal(email):
        token = identity.login(email, 'synthetic-password')['token']
        return identity.session(token), token
    boss, token = principal('owner@example.test')
    viewer, viewer_token = principal('member@example.test')
    stranger, stranger_token = principal('outsider@example.test')
    org = identity.organization(owner, 'Synthetic organization')
    other_org = identity.organization(outsider, 'Unrelated organization')
    projects = [app.state.projects.create('Synthetic '+name)['project_id'] for name in ('a', 'b', 'private', 'foreign')]
    for project in projects[:3]:
        identity.claim_project(boss, org, project)
    identity.claim_project(stranger, other_org, projects[3])
    for project, role in zip(projects[:2], ['viewer', 'engineer']):
        invitation = identity.invite(boss, project, viewer.email, role)['invitation_token']
        identity.accept(viewer, invitation)
    return app, boss, viewer, stranger, projects, token, viewer_token, stranger_token


def test_hosted_permissions_listing_reuse_grants_and_revocation(hosted):
    app, boss, viewer, stranger, (a, b, private, foreign), *_ = hosted
    library = app.state.source_library
    receipt = library.save(a, RAW, 'private-name.csv', ImportSelection.model_validate(SPEC), boss)
    hidden = library.save(private, RAW, 'hidden.csv', ImportSelection.model_validate(SPEC), boss)
    assert len(library.page(b, viewer)['entries']) == 1
    assert library.detail(b, receipt['entry']['entry_id'], viewer)['manifest']['filename'] == 'private-name.csv'
    with pytest.raises(Denied):
        library.detail(b, hidden['entry']['entry_id'], viewer)
    with pytest.raises(Denied):
        library.detail(foreign, receipt['entry']['entry_id'], stranger)
    with pytest.raises(Denied):
        library.save(a, RAW, 'blocked.csv', ImportSelection.model_validate(SPEC), viewer)
    with pytest.raises(Denied):
        library.reuse(a, receipt['entry']['entry_id'], viewer)
    copied = library.reuse(b, receipt['entry']['entry_id'], viewer)
    for digest in [copied['manifest']['file_sha256'], copied['source_sha256'], copied['entry']['manifest_sha256']]:
        app.state.identity.require_artifact(b, digest)
    app.state.identity.remove_member(boss, a, viewer.user_id)
    with pytest.raises(Denied):
        library.detail(b, receipt['entry']['entry_id'], viewer)
    assert library.detail(b, copied['entry']['entry_id'], viewer)['dataset'] == receipt['dataset']
    with artifact_scope(b):
        assert app.state.projects.artifacts.open(copied['manifest']['file_sha256']).read() == RAW


def test_hosted_same_user_other_organization_and_http_denial(hosted):
    app, boss, _viewer, _stranger, (a, b, _, foreign), token, viewer_token, stranger_token = hosted
    receipt = app.state.source_library.save(a, RAW, 'secret.csv', ImportSelection.model_validate(SPEC), boss)
    # Same principal can own two organizations; selecting one still cannot cross the boundary.
    second = app.state.identity.organization(boss.user_id, 'Second organization')
    target = app.state.projects.create('Second-org target')['project_id']
    app.state.identity.claim_project(boss, second, target)
    with pytest.raises(Denied, match='organization'):
        app.state.source_library.reuse(target, receipt['entry']['entry_id'], boss)
    client = TestClient(app)
    for suffix in ['', '/original', '/reuse']:
        method = client.post if suffix == '/reuse' else client.get
        response = method(f'/api/drone/projects/{foreign}/source-library/{receipt["entry"]["entry_id"]}{suffix}',
                          headers={'Authorization': 'Bearer '+stranger_token})
        assert response.status_code == 403 and 'secret.csv' not in response.text
    response = client.get(f'/api/drone/projects/{b}/source-library', headers={
        'Authorization': 'Bearer '+viewer_token, 'X-Organization-ID': second})
    assert response.status_code == 403
    assert client.get(f'/api/drone/projects/{a}/source-library', headers={'Authorization': 'Bearer '+token}).status_code == 200


def test_migration_newer_version_fails_closed_and_missing_entry(local):
    client, a, _ = local
    with pytest.raises(ProjectMissing):
        client.app.state.source_library.detail(a, '0' * 64)
    with client.app.state.metadata.connection(write=True) as db:
        db.execute('INSERT INTO source_library_migrations VALUES(2)')
    with pytest.raises(ValueError, match='migration'):
        SourceLibrary(client.app.state.metadata, client.app.state.projects)
