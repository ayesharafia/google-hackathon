"""Stored source corruption and before/after evidence, independently of browser rendering."""
import copy
import hashlib
import json

import pytest

from physimesh.drone.conditioning import condition_map
from physimesh.projects.performance import load_map, parse_map, retain_conditioned_map, retain_map
from physimesh.projects.realistic import fixture_policy, realistic_dataset
from tests.projects.test_local_studies import AUTH, client
from tests.projects.test_reports import retained


def test_browser_numeric_json_roundtrip_is_not_a_false_input_change():
    from physimesh.projects.reports import input_changes
    assert input_changes({'pressure': 101325., 'v': [0., 1.05]}, {'pressure': 101325, 'v': [0, 1.05]}) == []
    assert input_changes({'required': True}, {'required': 1})


def test_conditioned_history_validates_without_refitting_and_refuses_forged_envelope(tmp_path, monkeypatch):
    c = client(tmp_path)
    store = c.app.state.projects.artifacts
    raw = json.dumps(realistic_dataset(.01)).encode()
    digest = retain_map(store, raw)['source_sha256']
    conditioned = retain_conditioned_map(store, digest, fixture_policy())['source_sha256']
    def refuse(*args, **kwargs):
        pytest.fail('Reading retained coefficients must not refit with the current solver')
    monkeypatch.setattr('physimesh.drone.conditioning.linprog', refuse)
    model = load_map(store, conditioned)
    assert model.raw.configuration_id == 'synthetic-ct-cq-rotor'
    assert store.open(digest).read() == raw
    record = json.loads(store.open(conditioned).read())
    record['profile']['electrical_power_w'][5] *= .5
    forged = store.put_bytes(json.dumps(record).encode(), kind='test', meta={})
    with pytest.raises(ValueError, match='sample-envelope policy'):
        load_map(store, forged)


def test_power_shift_tolerance_is_declared_not_silently_relaxed():
    data = realistic_dataset(.01)
    data['points'][5]['power_w'] *= 5
    raw = parse_map(json.dumps(data).encode())
    with pytest.raises(ValueError, match='hull shift'):
        condition_map(raw, fixture_policy().model_copy(update={'max_power_shift_fraction': 0.}))


def test_geometry_endpoint_authentication_original_bytes_and_corruption(tmp_path):
    c = client(tmp_path)
    raw = b'solid fixture\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid fixture\n'
    digest = c.app.state.projects.artifacts.put_bytes(raw, kind='stl', meta={})
    route = '/api/drone/projects/geometry-sources/'+digest
    assert c.get(route).status_code == 401
    response = c.get(route, headers=AUTH)
    assert response.status_code == 200 and response.content == raw
    assert response.headers['X-Geometry-Source-SHA256'] == hashlib.sha256(raw).hexdigest()
    (tmp_path/'artifacts/objects'/digest[:2]/digest).write_bytes(raw+b'corrupt')
    assert c.get(route, headers=AUTH).status_code == 422


def test_comparison_names_constraint_changes_on_frozen_cases(tmp_path):
    c = client(tmp_path)
    project, base, before = retained(c)
    snapshot = json.loads(project['snapshot_json'])
    snapshot['mission']['payload_positions_body_m'] = [[.8, 0., 0.]]
    assert c.put(base+'/draft', headers=AUTH, json={'expected_version': 1, 'snapshot_json': json.dumps(snapshot)}).status_code == 200
    revision = c.post(base+'/revisions', headers=AUTH, json={'expected_version': 2}).json()
    after = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': revision['revision_sha256']}).json()
    report = c.post(base+'/comparisons', headers=AUTH, json={'before': before['study_sha256'], 'after': after['study_sha256']}).json()
    changes = report['constraint_changes']
    assert any(row['newly_active'] for row in changes)
    for row in changes:
        old, new = set(row['before_active_constraints']), set(row['after_active_constraints'])
        assert row['newly_active'] == sorted(new-old)
        assert row['no_longer_active'] == sorted(old-new)
    changed = copy.deepcopy(after)
    changed['specification']['model']['source_fingerprint_sha256'] = 'f'*64
    from physimesh.projects.reports import compare_records
    assert all(row['case_payload_change_kg'] is None for row in compare_records(before, changed, {}, {})['constraint_changes'])
