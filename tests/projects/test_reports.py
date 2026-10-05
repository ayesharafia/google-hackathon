import copy
import hashlib
import json

import pytest

from physimesh.projects.reports import compare_records, input_changes, render_pdf
from tests.projects.test_local_studies import AUTH, client


def retained(c):
    project = c.post('/api/drone/projects/examples/hover', headers=AUTH).json()
    base = '/api/drone/projects/' + project['project_id']
    frozen = c.post(base+'/revisions', headers=AUTH, json={'expected_version': 1}).json()
    report = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen['revision_sha256']}).json()
    return project, base, report


def test_pdf_binds_verified_bytes_and_is_deterministic_without_solver(tmp_path, monkeypatch):
    c = client(tmp_path)
    _, base, report = retained(c)
    def refuse(*args, **kwargs):
        pytest.fail('report must not execute the solver')
    monkeypatch.setattr('physimesh.projects.studies.capacity_from_snapshot', refuse)
    study = report['study_sha256']
    raw = c.get(base+'/studies/'+study+'/export', headers=AUTH).content
    pdf = c.get(base+'/studies/'+study+'/pdf', headers=AUTH)
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-')
    assert pdf.headers['X-Study-JSON-SHA256'] == hashlib.sha256(raw).hexdigest()
    assert pdf.headers['X-PDF-SHA256'] == hashlib.sha256(pdf.content).hexdigest()
    assert pdf.content == c.get(base+'/studies/'+study+'/pdf', headers=AUTH).content
    assert c.get(base+'/studies/'+study+'/pdf').status_code == 401
    assert c.get('/api/drone/projects/other/studies/'+study+'/pdf', headers=AUTH).status_code == 404
    digest = c.get(base, headers=AUTH).json()['studies'][0]['result_sha256']
    path = tmp_path/'artifacts/objects'/digest[:2]/digest
    path.write_bytes(path.read_bytes()+b' ')
    assert c.get(base+'/studies/'+study+'/pdf', headers=AUTH).status_code == 422


def test_corrupt_retained_pdf_refuses_export(tmp_path):
    c = client(tmp_path)
    _, base, record = retained(c)
    route = base+'/studies/'+record['study_sha256']+'/pdf'
    response = c.get(route, headers=AUTH)
    digest = response.headers['X-PDF-SHA256']
    path = tmp_path/'artifacts/objects'/digest[:2]/digest
    path.write_bytes(path.read_bytes()+b' ')
    assert c.get(route, headers=AUTH).status_code == 422


def test_evidence_json_roundtrip_keeps_vectors_unicode_and_boolean():
    from physimesh.projects.reports import evidence_lines
    record = {'a': [True, None, 0., '\u0394'], 'nested': [{'vector': [1, 2, 3]}, []]}
    assert json.loads('\n'.join(evidence_lines(record))) == record
    assert input_changes({'required': True}, {'required': 1})


def test_compare_retained_inputs_ignores_mutable_draft_and_refuses_cross_project(tmp_path):
    c = client(tmp_path)
    project, base, first = retained(c)
    snapshot = json.loads(project['snapshot_json'])
    snapshot['mission']['payload_positions_body_m'] = [[.4, 0, 0]]
    c.put(base+'/draft', headers=AUTH, json={'expected_version': 1, 'snapshot_json': json.dumps(snapshot)})
    revision = c.post(base+'/revisions', headers=AUTH, json={'expected_version': 2}).json()
    second = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': revision['revision_sha256']}).json()
    body = {'before': first['study_sha256'], 'after': second['study_sha256']}
    comparison = c.post(base+'/comparisons', headers=AUTH, json=body)
    assert comparison.status_code == 200
    result = comparison.json()
    assert result['comparable_numeric_results']
    assert result['input_changes'] == [{'path': '/mission/payload_positions_body_m', 'kind': 'changed',
                                     'before': [[0., 0., 0.]], 'after': [[.4, 0, 0]]}]
    assert result['payload_change_kg'] == second['payload_lower_bound_kg']-first['payload_lower_bound_kg']
    snapshot['mission']['payload_positions_body_m'] = [[.9, 0, 0]]
    c.put(base+'/draft', headers=AUTH, json={'expected_version': 2, 'snapshot_json': json.dumps(snapshot)})
    assert c.post(base+'/comparisons', headers=AUTH, json=body).json() == result
    _, other, _ = retained(c)
    assert c.post(other+'/comparisons', headers=AUTH, json=body).status_code == 404
    assert c.post(base+'/comparisons', json=body).status_code == 401


def test_comparison_withholds_numeric_delta_across_model_scope_outcome_or_semantics(tmp_path):
    c = client(tmp_path)
    _, _, record = retained(c)
    for field in ('model', 'mission_semantics', 'data_scope', 'outcome', 'schema_version'):
        changed = copy.deepcopy(record)
        if field == 'model':
            changed['specification']['model']['source_fingerprint_sha256'] = 'f'*64
        else:
            changed[field] = 'different'
        result = compare_records(record, changed, {}, {})
        assert not result['comparable_numeric_results'] and result['payload_change_kg'] is None


def test_comparison_pointer_escaping_absence_and_bound():
    assert input_changes({'a/b': None}, {'a/b': 0, '~': 1}) == [
        {'path': '/a~1b', 'kind': 'changed', 'before': None, 'after': 0},
        {'path': '/~0', 'kind': 'added', 'after': 1}]
    with pytest.raises(ValueError, match='500'):
        input_changes({}, {str(n): n for n in range(501)})


def test_pdf_refusal_unicode_and_markup_are_visible_as_text(tmp_path):
    c = client(tmp_path)
    _, _, record = retained(c)
    record['outcome'] = 'unsupported'
    record['payload_lower_bound_kg'] = None
    record['reasons'] = ['Unknown <b>measurement</b> & source \u0394']
    assert render_pdf(json.dumps(record).encode(), '{}').startswith(b'%PDF-')
    with pytest.raises(ValueError, match='bounded PDF'):
        render_pdf(json.dumps(record).encode(), json.dumps({'oversize': 'x'*1_000_001}))


def test_renderer_source_change_changes_pdf_bytes_and_retained_metadata_agrees(tmp_path, monkeypatch):
    c = client(tmp_path)
    _, base, report = retained(c)
    route = base+'/studies/'+report['study_sha256']+'/pdf'
    first = c.get(route, headers=AUTH)
    monkeypatch.setattr('physimesh.projects.reports.RENDERER_SOURCE_SHA256', 'f'*64)
    second = c.get(route, headers=AUTH)
    assert first.content != second.content
    assert first.headers['X-PDF-SHA256'] != second.headers['X-PDF-SHA256']
    for response in (first, second):
        assert response.status_code == 200
        digest = response.headers['X-PDF-SHA256']
        metadata = c.app.state.projects.artifacts.meta(digest)
        assert metadata['renderer_source_sha256'] == response.headers['X-Report-Renderer-SHA256']
        assert metadata['study_json_sha256'] == response.headers['X-Study-JSON-SHA256']
        assert hashlib.sha256(response.content).hexdigest() == digest
