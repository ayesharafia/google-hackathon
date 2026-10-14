"""Failure/privacy checks for isolated submission diagnostics (no service required)."""
import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('submission_profile',
    Path(__file__).resolve().parents[1]/'scripts/qa/submission_profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class SubmissionDiagnosticsTests(unittest.TestCase):
    def test_spans_restore_methods_and_do_not_record_arguments_or_errors(self):
        class Target:
            def run(self, secret):
                raise ValueError(secret)
        target = Target()
        observations = []
        original = target.run
        with self.assertRaisesRegex(ValueError, 'secret-token'), profile.stage_spans(
                [(target, 'run', 'admission')], observations):
            target.run('secret-token')
        self.assertEqual(target.run, original)
        self.assertNotIn('run', target.__dict__)
        self.assertEqual(observations[0]['stage'], 'admission')
        self.assertFalse(observations[0]['returned'])
        self.assertGreaterEqual(observations[0]['elapsed_ms'], 0)
        self.assertNotIn('secret-token', json.dumps(observations))

    def test_restore_existing_instance_override_after_partial_setup_failure(self):
        class Target:
            def run(self):
                return 'original'
        target = Target()
        override = lambda: 'override'
        target.run = override
        with self.assertRaises(AttributeError), profile.stage_spans(
                [(target, 'run', 'ok'), (target, 'missing', 'bad')], []):
            pass
        self.assertIs(target.run, override)

    def test_non_acceptance_and_transport_failures_are_retained_without_body(self):
        class Response:
            status_code = 503
            content = b'private design and token'
        class Client:
            def post(self, *args, **kwargs):
                return Response()
        observation, job = profile.observe_submission(Client(), '/synthetic', 'revision')
        self.assertEqual(observation['status'], 503)
        self.assertFalse(observation['accepted_queued'])
        self.assertIsNone(job)
        self.assertNotIn('private', json.dumps(observation))
        class Broken:
            def post(self, *args, **kwargs):
                raise RuntimeError('credential=SECRET')
        observation, _ = profile.observe_submission(Broken(), '/synthetic', 'revision')
        self.assertEqual(observation['status'], 0)
        self.assertEqual(observation['error'], 'request_exception')
        self.assertNotIn('SECRET', json.dumps(observation))

    def test_202_requires_queued_state_and_valid_job_body(self):
        class Response:
            status_code = 202
            content = b'buffered'
            def json(self):
                return {'job_id': 'job_test', 'state': 'cancelled', 'spec_json': 'PRIVATE'}
        class Client:
            def post(self, *args, **kwargs):
                return Response()
        observation, job = profile.observe_submission(Client(), '/synthetic', 'revision')
        self.assertFalse(observation['accepted_queued'])
        self.assertEqual(job, 'job_test')
        self.assertNotIn('PRIVATE', json.dumps(observation))
        self.assertEqual(observation['response_bytes'], 8)

    def test_cancellation_failure_is_retained_without_sensitive_message(self):
        class Client:
            def post(self, *args, **kwargs):
                raise RuntimeError('private-credentials')
        result = profile.cancel_observation(Client(), '/synthetic', 'job_test')
        self.assertFalse(result['cancelled'])
        self.assertEqual(result['cancellation_error'], 'cancellation_exception')
        self.assertNotIn('private-credentials', json.dumps(result))

    def test_repeat_budget_precedes_imports_or_resource_creation(self):
        for value in (0, 21):
            with self.assertRaises(ValueError):
                profile.run(Path('/absent'), value)


if __name__ == '__main__':
    unittest.main()
