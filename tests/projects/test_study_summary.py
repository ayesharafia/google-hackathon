"""Read-only retained-study summaries preserve engineering claim boundaries."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.atmosphere import G0
from physimesh.drone.provenance import canonical_json
from physimesh.projects.contracts import DesignRevisionV1
from tests.projects.test_local_studies import AUTH, client
from tests.projects.test_scenario_limits import cap, scenario


def saved_study(tmp_path, *, change=None, extended=False):
    c = client(tmp_path)
    project = c.post('/api/drone/projects/examples/hover', headers=AUTH).json()
    snapshot = json.loads(project['snapshot_json'])
    if extended:
        snapshot['fidelity']['local_pilot']['model_version'] = 'convex_axial_capacity_v2'
    if change:
        change(snapshot)
    base = '/api/drone/projects/'+project['project_id']
    saved = c.put(base+'/draft', headers=AUTH, json={
        'expected_version': project['draft_version'], 'snapshot_json': json.dumps(snapshot)})
    assert saved.status_code == 200, saved.text
    frozen = c.post(base+'/revisions', headers=AUTH,
                    json={'expected_version': saved.json()['draft_version']})
    assert frozen.status_code == 200, frozen.text
    result = c.post(base+'/studies', headers=AUTH,
                   json={'revision_sha256': frozen.json()['revision_sha256']})
    assert result.status_code == 200, result.text
    record = result.json()
    route = base+'/studies/'+record['study_sha256']
    return c, base, route, snapshot, record


def test_summary_binds_exact_retained_bytes_and_frozen_design_after_edit_restart(tmp_path, monkeypatch):
    c, base, route, snapshot, record = saved_study(tmp_path)
    original = c.get(route+'/export', headers=AUTH).content
    snapshot['masses']['items'][0]['mass_kg'] = 99
    current = c.get(base, headers=AUTH).json()
    assert c.put(base+'/draft', headers=AUTH, json={'expected_version': current['draft_version'],
                 'snapshot_json': json.dumps(snapshot)}).status_code == 200

    def forbid_model(*args, **kwargs):
        pytest.fail('A retained summary must not run the current numerical model')

    monkeypatch.setattr('physimesh.projects.studies.capacity_from_snapshot', forbid_model)
    c = client(tmp_path)
    response = c.get(route+'/summary', headers=AUTH)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary['schema_version'] == 'study_summary_v1'
    assert summary['study_json_sha256'] == hashlib.sha256(original).hexdigest()
    assert summary['study_sha256'] == record['study_sha256']
    for name in ('project_id', 'revision_sha256', 'snapshot_sha256'):
        assert summary[name] == record['specification'][name]
    assert summary['model_version'] == record['model_version']
    assert summary['result_schema_version'] == 'local_mission_capacity_v3'
    # E=2*100*3600*.8*.8; long hover P=E/300; T=P/10; empty mass=12.
    assert summary['bounds']['nominal']['payload_kg'] == pytest.approx(153.6/G0-12)
    assert summary['bounds']['scenario']['status'] == 'not_declared'
    assert summary['bounds']['allowable']['payload_kg'] is None
    assert summary['engineering_approval'] == 'pending'
    assert summary['data_scope'] == 'analytic_fixture'
    assert summary['historical'] is False
    assert summary['qualification'] == record['qualification']
    assert summary['performance_source_sha256'] == record['specification']['performance_source_sha256']
    assert {case['case_id'] for case in summary['cases']} == {case['case_id'] for case in record['cases']}
    for case, original_case in zip(summary['cases'], record['cases'], strict=True):
        assert case['active_constraints'] == original_case['active_constraints']
    assert c.get(route+'/export', headers=AUTH).content == original
    assert len(c.get(base, headers=AUTH).json()['studies']) == 1


@pytest.mark.parametrize('mode', ['supported', 'incomplete', 'proposed', 'unresolved_cap'])
def test_v4_summary_keeps_nominal_scenario_and_allowable_claims_distinct(tmp_path, mode):
    def change(snapshot):
        settings = snapshot['fidelity']['local_pilot']
        if mode == 'supported':
            settings.update(scenarios=[scenario(mass_items_kg={'structure': 11.})],
                            allowable_caps=[cap(1.)])
        elif mode == 'incomplete':
            settings.update(scenarios=[scenario(atmosphere={'pressure_pa': 90000.,
                'temperature_k': 288.15, 'source': 'Synthetic atmosphere outside fixed-map coverage'})],
                allowable_caps=[cap(1.)])
        elif mode == 'proposed':
            settings['allowable_caps'] = [cap(1., status='proposed')]
        else:
            for case in snapshot['mission']['cases']:
                case['body_force_body_n'] = [0., 0., 200.]
            settings['allowable_caps'] = [cap(0.)]

    c, _, route, _, record = saved_study(tmp_path, change=change, extended=True)
    response = c.get(route+'/summary', headers=AUTH)
    assert response.status_code == 200, response.text
    summary = response.json(); bounds = summary['bounds']
    assert summary['result_schema_version'] == 'local_mission_capacity_v4'
    assert summary['outcome'] == 'feasible'
    assert bounds['nominal']['payload_kg'] == record['payload_lower_bound_kg']
    assert bounds['scenario']['status'] == record['scenario_analysis']['status']
    assert bounds['allowable']['status'] == record['external_allowables']['status']
    assert bounds['allowable']['approval_authentication'] == 'not_authenticated'
    assert summary['engineering_approval'] == 'pending'
    assert bounds['allowable']['declared_cap_kg'] == record['external_allowables']['declared_approved_cap_kg']
    for bound in bounds.values():
        assert bound['label'].strip() and bound['qualification'].strip()
    if mode == 'supported':
        assert bounds['nominal']['payload_kg'] == pytest.approx(153.6/G0-12)
        assert bounds['scenario']['payload_kg'] == pytest.approx(153.6/G0-13)
        assert bounds['allowable']['payload_kg'] == 1.
        assert bounds['scenario']['limiting_ids'] == ['heavier']
        assert summary['scenarios'][0]['correlation_note'] == scenario()['correlation_note']
    elif mode == 'incomplete':
        assert bounds['scenario']['payload_kg'] is None
        assert bounds['allowable']['payload_kg'] is None
        assert summary['scenarios'][0]['outcome'] == 'unsupported'
        assert summary['scenarios'][0]['payload_kg'] is None
    elif mode == 'proposed':
        assert bounds['allowable']['status'] == 'no_declared_approved_cap'
        assert bounds['allowable']['payload_kg'] is None
        assert bounds['allowable']['declared_cap_kg'] is None
    else:
        assert bounds['allowable']['status'] == 'unresolved'
        assert bounds['allowable']['declared_cap_kg'] == 0
        assert bounds['allowable']['payload_kg'] is None


@pytest.mark.parametrize('outcome', ['infeasible', 'unsupported', 'unresolved'])
def test_projection_never_promotes_failed_outcome_to_numeric_capacity(tmp_path, outcome):
    from physimesh.projects.study_summary import summarize_study

    _, _, _, _, record = saved_study(tmp_path)
    # Unit projection probe, not a manufactured accepted engineering result.
    record['outcome'] = outcome
    for case in record['cases']:
        case['outcome'] = outcome
    summary = summarize_study(canonical_json(record).encode())
    assert summary['outcome'] == outcome
    assert summary['bounds']['nominal']['payload_kg'] is None
    assert all(case['payload_kg'] is None for case in summary['cases'])


def test_summary_requires_auth_project_association_and_verified_result_bytes(tmp_path):
    c, _, route, _, _ = saved_study(tmp_path)
    assert c.get(route+'/summary').status_code == 401
    other = c.post('/api/drone/projects', headers=AUTH, json={'title': 'Other project'}).json()
    cross_project = '/api/drone/projects/'+other['project_id']+'/studies/'+route.rsplit('/', 1)[-1]+'/summary'
    assert c.get(cross_project, headers=AUTH).status_code == 404
    raw = c.get(route+'/export', headers=AUTH).content
    digest = hashlib.sha256(raw).hexdigest()
    path = tmp_path/'artifacts/objects'/digest[:2]/digest
    path.write_bytes(raw+b' ')
    response = c.get(route+'/summary', headers=AUTH)
    assert response.status_code == 422 and 'integrity' in response.text


def test_summary_requires_retained_frozen_revision(tmp_path):
    c, _, route, _, record = saved_study(tmp_path)
    with sqlite3.connect(tmp_path/'projects.sqlite') as db:
        db.execute('DELETE FROM design_revisions WHERE revision_sha256=?',
                   (record['specification']['revision_sha256'],))
    assert c.get(route+'/summary', headers=AUTH).status_code == 404


def test_historical_v2_summary_preserves_bytes_scope_and_never_recomputes(tmp_path, monkeypatch):
    fixture = json.loads((Path(__file__).parent/'fixtures/retained-v2-sequence.json').read_text())
    raw = fixture['original_result_json'].encode(); record = json.loads(raw)
    revision = DesignRevisionV1.model_validate_json(canonical_json(fixture['revision']))
    c = client(tmp_path); pid = revision.project_id
    c.app.state.projects.artifacts.put_bytes(raw, kind='historical_fixture', meta={})
    with sqlite3.connect(tmp_path/'projects.sqlite') as db:
        db.execute('INSERT INTO project_meta VALUES(?,?,?,?,?,?)',
                   (pid, 'Retained historical fixture', 2, revision.snapshot_json,
                    revision.created_utc, revision.created_utc))
        db.execute('INSERT INTO design_revisions VALUES(?,?,?,?,?)',
                   (pid, 2, revision.readiness_purpose, revision.revision_sha256(),
                    canonical_json(fixture['revision']).encode()))
        db.execute('INSERT INTO local_studies VALUES(?,?,?,?,?)',
                   (pid, revision.revision_sha256(), record['study_sha256'], fixture['result_sha256'],
                    revision.created_utc))

    def forbid_model(*args, **kwargs):
        pytest.fail('Historical summary must not execute or requalify the current model')

    monkeypatch.setattr('physimesh.projects.studies.capacity_from_snapshot', forbid_model)
    route = '/api/drone/projects/'+pid+'/studies/'+record['study_sha256']
    response = c.get(route+'/summary', headers=AUTH)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary['historical'] is True
    assert summary['result_schema_version'] == 'local_mission_capacity_v2'
    assert summary['study_json_sha256'] == fixture['result_sha256']
    assert summary['qualification'] == record['qualification']
    assert summary['engineering_approval'] == record['engineering_approval']
    assert c.get(route+'/export', headers=AUTH).content == raw


def test_hosted_summary_denies_outsider_and_does_not_promote_workflow_review(tmp_path):
    from physimesh.platform.scoped_artifacts import artifact_scope

    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', '', None, hosted_mode=True))
    identity = app.state.identity
    owner = identity.provision('owner@example.test', password='synthetic-password')
    identity.provision('outsider@example.test', password='synthetic-password')
    owner_token = identity.login('owner@example.test', 'synthetic-password')['token']
    outsider_token = identity.login('outsider@example.test', 'synthetic-password')['token']
    org = identity.organization(owner, 'Summary scope fixture')
    headers = {'Authorization': 'Bearer '+owner_token, 'X-Organization-ID': org}
    with TestClient(app) as c:
        project = c.post('/api/drone/projects/examples/hover', headers=headers).json()
        pid = project['project_id']
        with artifact_scope(pid):
            frozen = app.state.projects.freeze(pid, project['draft_version'], 'screening')
            study = app.state.studies.run(pid, frozen['revision_sha256'])
        route = '/api/drone/projects/'+pid+'/studies/'+study['study_sha256']+'/summary'
        assert c.get(route, headers={'Authorization': 'Bearer '+outsider_token}).status_code == 403
        before = c.get(route, headers=headers)
        assert before.status_code == 200, before.text
        review = c.post('/api/drone/platform/reviews/'+pid, headers=headers,
                        json={'study_sha256': study['study_sha256'], 'decision': 'accepted',
                              'comment': 'Synthetic workflow review only, no physics acceptance'})
        assert review.status_code == 201, review.text
        after = c.get(route, headers=headers)
        assert after.json() == before.json()
        assert after.json()['engineering_approval'] == 'pending'
        assert c.post('/api/drone/platform/logout', headers=headers).status_code == 200
        assert c.get(route, headers=headers).status_code == 401


def test_pdf_cache_tracks_summary_dependency_and_retains_previous_bytes(tmp_path, monkeypatch):
    from physimesh.projects import reports

    c, _, route, _, _ = saved_study(tmp_path)
    original_json = c.get(route+'/export', headers=AUTH).content
    original_pdf = c.get(route+'/pdf', headers=AUTH)
    assert original_pdf.status_code == 200, original_pdf.text
    previous_pdf_digest = original_pdf.headers['X-PDF-SHA256']
    previous_summary_digest = reports.SUMMARY_SOURCE_SHA256
    real_summary, real_render = reports.summarize_study, reports.render_pdf
    rendered = []

    def changed_presentation(raw):
        projection = real_summary(raw)
        projection['bounds']['nominal']['label'] += ' (presentation fixture)'
        return projection

    def tracked_render(*args):
        rendered.append(True)
        return real_render(*args)

    # Simulate a later presentation implementation without altering source files,
    # retained model/results, or the previous PDF receipt.
    monkeypatch.setattr(reports, 'SUMMARY_SOURCE_SHA256', 'f'*64)
    monkeypatch.setattr(reports, 'summarize_study', changed_presentation)
    monkeypatch.setattr(reports, 'render_pdf', tracked_render)
    revised_pdf = c.get(route+'/pdf', headers=AUTH)
    assert revised_pdf.status_code == 200, revised_pdf.text
    assert rendered == [True]
    assert revised_pdf.content != original_pdf.content
    assert c.get(route+'/pdf', headers=AUTH).content == revised_pdf.content
    assert rendered == [True]
    assert c.get(route+'/export', headers=AUTH).content == original_json
    with c.app.state.projects.artifacts.open(previous_pdf_digest) as retained:
        assert retained.read() == original_pdf.content
    with sqlite3.connect(tmp_path/'projects.sqlite') as db:
        stored = db.execute('SELECT pdf_sha256,receipt FROM report_cache').fetchall()
        receipts = [json.loads(row[1]) for row in stored]
    assert len(receipts) == 2
    assert {r['summary_source_sha256'] for r in receipts} == {previous_summary_digest, 'f'*64}
    assert previous_pdf_digest in {row[0] for row in stored}
    assert any(r['summary_source_sha256'] == 'f'*64 for r in receipts)
