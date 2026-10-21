"""Pure runner accounting tests; no cloud, aircraft or resource qualification."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'bounded_soak_target', Path(__file__).resolve().parents[1]/'scripts/qa/bounded_soak.py')
soak = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = soak
SPEC.loader.exec_module(soak)


class Response:
    def __init__(self, body=None, status=200, content=None):
        self.body, self.status_code = body, status
        self.content = content if content is not None else json.dumps(body).encode()

    def json(self):
        return self.body


class Client:
    def __init__(self, responses):
        self.responses, self.headers = iter(responses), {}

    def request(self, *_args, **_kwargs):
        return next(self.responses)


def fixture_responses():
    return [Response({'token': 'synthetic-secret'}),
            Response({'project_id': 'p', 'draft_version': 0,
                      'snapshot_json': json.dumps({'identity': {}})}, 201),
            Response({'draft_version': 1}), Response({'revision_sha256': 'r'}),
            Response({'job_id': 'study'}, 202),
            Response({'state': 'succeeded', 'result_json': json.dumps({'study_sha256': 's'})}),
            Response({'outcome': 'feasible'}), Response({'job_id': 'pdf'}, 202),
            Response({'state': 'succeeded', 'result_json': '{}'}),
            Response(content=b'%PDF-synthetic'), Response(content=b'%PDF-synthetic'),
            Response({}), Response({})]


def test_one_full_journey_and_request_accounting():
    calls = []
    reports = []
    runner = soak.Runner(Client(fixture_responses()), lambda: calls.append('work') or True,
                         soak.Budgets(journeys=1), lambda value: reports.append(json.loads(json.dumps(value))))
    report = runner.execute('synthetic-password', 'org')
    assert report['stop_reason'] == 'journey_budget'
    assert report['completed_journeys'] == 1 and report['requests'] == 13
    assert calls == ['work', 'work']
    assert reports[0]['request_observations'][0]['error'] == 'unfinished_request'
    assert all(item['error'] is None for item in report['request_observations'])
    assert 'synthetic-secret' not in json.dumps(report)
    assert 'synthetic-password' not in json.dumps(report)


def test_request_ceiling_does_not_start_next_work():
    calls = []
    report = soak.Runner(Client(fixture_responses()), lambda: calls.append(True),
                         soak.Budgets(requests=1)).execute('password', 'org')
    assert report['stop_reason'] == 'request_budget'
    assert report['completed_journeys'] == 0 and report['requests'] == 1
    assert report['failures'] == 0 and not calls


def test_worker_failure_retains_accepted_submission_without_claiming_completion():
    report = soak.Runner(Client(fixture_responses()), lambda: False,
                         soak.Budgets(journeys=1)).execute('password', 'org')
    assert report['stop_reason'] == 'worker_did_not_claim'
    assert report['requests'] == 5 and report['completed_journeys'] == 0 and report['failures'] == 1


def test_bad_pdf_is_not_complete_journey():
    responses = fixture_responses()
    responses[9] = Response(content=b'not-a-pdf')
    report = soak.Runner(Client(responses), lambda: True,
                         soak.Budgets(journeys=1)).execute('password', 'org')
    assert report['stop_reason'] == 'pdf_integrity_mismatch'
    assert report['requests'] == 10 and report['completed_journeys'] == 0


def test_http_failure_is_safe():
    report = soak.Runner(Client([Response({'private': 'secret'}, 403)]), lambda: True,
                         soak.Budgets(journeys=1)).execute('password', 'org')
    assert report['failures'] == 1 and report['stop_reason'] == 'http_error'
    assert report['request_observations'][0]['status'] == 403
    assert 'private' not in json.dumps(report) and 'secret' not in json.dumps(report)


@pytest.mark.parametrize('field,value', [('requests', 1.5), ('journeys', True),
                                         ('storage_bytes', 0), ('memory_bytes', 2*1024**3+1),
                                         ('journeys', 21), ('requests', 1001)])
def test_invalid_integer_and_resource_budgets(field, value):
    with pytest.raises(ValueError):
        soak.Budgets(**{field: value}).validate()


def test_existing_receipt_is_not_overwritten(tmp_path):
    path = tmp_path/'receipt.json'
    path.write_text('original')
    with pytest.raises(SystemExit):
        soak.main(['--receipt', str(path)])
    assert path.read_text() == 'original'


def test_descendant_discovery_excludes_unrelated_processes():
    owned = {10: 100}
    table = {10: (1, 100, 10, 20), 11: (10, 200, 10, 20),
             12: (11, 300, 10, 20), 13: (1, 400, 10, 20)}
    soak.discover(table, owned)
    assert owned == {10: 100, 11: 200, 12: 300}


def test_internal_child_rejects_invalid_budget_before_setup(tmp_path):
    root = tmp_path/'not-created'
    with pytest.raises(ValueError):
        soak.child(root, soak.Budgets(requests=0))
    assert not root.exists()
