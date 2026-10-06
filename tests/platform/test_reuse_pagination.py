import json
from contextlib import contextmanager

import pytest

from physimesh.projects.reports import report_identity
from tests.projects.test_local_studies import AUTH, client
from tests.projects.test_reports import retained


def test_verified_reuse_never_recomputes_accepted_spec_and_refuses_corrupt_sources(tmp_path, monkeypatch):
    c = client(tmp_path)
    project, base, record = retained(c)
    rev = record['specification']['revision_sha256']
    def refuse(*args, **kwargs):
        pytest.fail('identical accepted specification must not recompute')
    monkeypatch.setattr('physimesh.projects.studies.capacity_from_snapshot', refuse)
    repeated = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': rev})
    assert repeated.status_code == 200 and repeated.json() == record
    digest = json.loads(project['snapshot_json'])['rotors'][0]['map_ref']
    path = tmp_path/'artifacts/objects'/digest[:2]/digest
    path.write_bytes(path.read_bytes()+b' ')
    refused = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': rev})
    assert refused.status_code == 422 and 'integrity' in refused.text
    # Historical evidence remains readable despite loss of an original source object.
    assert c.get(base+'/studies/'+record['study_sha256'], headers=AUTH).json() == record


def test_pdf_reuse_renderer_change_and_corrupt_cache_receipt(tmp_path, monkeypatch):
    c = client(tmp_path)
    _, base, record = retained(c)
    path = base+'/studies/'+record['study_sha256']+'/pdf'
    first = c.get(path, headers=AUTH)
    from physimesh.projects import reports
    original = reports.render_pdf
    calls = []
    def renderer(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(reports, 'render_pdf', renderer)
    assert c.get(path, headers=AUTH).content == first.content and calls == []
    monkeypatch.setattr(reports, 'REPORT_VERSION', 'fixture_renderer_upgrade')
    changed = c.get(path, headers=AUTH)
    assert changed.status_code == 200 and len(calls) == 1
    assert c.get(path, headers=AUTH).content == changed.content and len(calls) == 1
    repository = c.app.state.projects.repository
    raw, snapshot = c.app.state.studies.report_inputs(base.split('/')[-1], record['study_sha256'])
    from physimesh.drone.provenance import sha256_record
    key = sha256_record(report_identity(raw, snapshot))
    with repository._connection(write=True) as db:
        db.execute('UPDATE report_cache SET receipt=? WHERE cache_key=?', ('{}', key))
    response = c.get(path, headers=AUTH)
    assert response.status_code == 422 and 'receipt integrity' in response.text


def test_inventory_keyset_pages_have_bounded_queries_payload_and_no_duplicates(tmp_path, monkeypatch):
    c = client(tmp_path)
    p = c.post('/api/drone/projects', headers=AUTH, json={'title': 'synthetic scale seed'}).json()
    repository = c.app.state.projects.repository
    # Persist through the adapter, using a valid immutable schema fixture.
    for n in range(999):
        repository.create(f'Synthetic inventory {n}', p['snapshot_json'])
    query_count = []
    original = repository._connection
    @contextmanager
    def connection(**kwargs):
        with original(**kwargs) as db:
            db.set_trace_callback(query_count.append)
            yield db
    monkeypatch.setattr(repository, '_connection', connection)
    ids, cursor = [], ''
    while True:
        query_count.clear()
        response = c.get('/api/drone/projects', headers=AUTH, params={'limit': 100, 'after': cursor})
        assert response.status_code == 200
        page = response.json()
        assert len(page['projects']) <= 100 and len(response.content) < 40000
        assert all('snapshot_json' not in row and 'studies' not in row for row in page['projects'])
        assert len([sql for sql in query_count if sql.startswith('SELECT')]) == 1
        ids.extend(row['project_id'] for row in page['projects'])
        if not page['next_cursor']:
            break
        cursor = page['next_cursor']
    assert len(ids) == len(set(ids)) == 1000
    assert len(c.get('/api/drone/projects', headers=AUTH).json()['projects']) == 25
    for params in ({'limit': 0}, {'limit': 101}, {'after': 'not-base64'}):
        assert c.get('/api/drone/projects', headers=AUTH, params=params).status_code == 422


def test_detail_histories_bound_and_old_entries_remain_readable(tmp_path):
    c = client(tmp_path)
    project, base, record = retained(c)
    repo = c.app.state.projects.repository
    pid = project['project_id']
    first = repo.revision(pid, record['specification']['revision_sha256'])
    # Valid revisions differ by retained timestamp; SQL bypass only avoids duplicate authoring work.
    from physimesh.projects.serialization import dump_contract
    with repo._connection(write=True) as db:
        for n in range(1, 101):
            revision = first.model_copy(update={'created_utc': f'2026-10-06T01:{n//60:02d}:{n%60:02d}Z'})
            db.execute('INSERT INTO design_revisions VALUES(?,?,?,?,?)',
                       (pid, n+1, 'screening', revision.revision_sha256(), dump_contract(revision)))
    view = c.get(base, headers=AUTH).json()
    assert len(view['revisions']) == 25 and view['revisions_more']
    seen, after = [], ''
    while True:
        page = c.get(base+'/history/revisions', headers=AUTH, params={'limit': 25, 'after': after}).json()
        seen.extend(r['revision_sha256'] for r in page['revisions'])
        if not page['next_cursor']:
            break
        after = page['next_cursor']
    assert len(seen) == len(set(seen)) == 101
    assert c.get(base+'/revisions/'+seen[-1], headers=AUTH).status_code == 200
