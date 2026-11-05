"""Execute exact middleware AST in isolation while full app source is recovered.

This checks the actual route guard, not application construction, real identity
storage or full hosted integration. Full app tests remain a separate gate.
"""
import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from physimesh.api.atmosphere import router
from physimesh.drone.standard_atmosphere import MODEL_ID


class InvalidSession(Exception):
    pass


class Denied(Exception):
    pass


class Overloaded(Exception):
    pass


@contextmanager
def artifact_scope(project):
    yield


async def run_in_threadpool(func, *args, **kwargs):
    return func(*args, **kwargs)


class Connection:
    def execute(self, *args):
        return self

    def fetchone(self):
        return None


@contextmanager
def connection():
    yield Connection()


def guarded_client(hosted):
    path = Path(__file__).resolve().parents[2] / 'src/physimesh/api/app.py'
    tree = ast.parse(path.read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                and n.name == 'protect_drone_routes')
    node.decorator_list = []
    app = FastAPI()
    app.include_router(router)
    app.state.browser_sessions = None
    app.state.settings = SimpleNamespace(hosted_mode=hosted)
    app.state.hosted_signin = None
    app.state.oidc = None
    app.state.metadata = SimpleNamespace(connection=connection)
    def session(token):
        if token != 'valid':
            raise InvalidSession('invalid session')
        return SimpleNamespace(session_hash='synthetic', user_id='synthetic')
    app.state.identity = SimpleNamespace(session=session)
    scope = {
        'app': app,
        'settings': SimpleNamespace(hosted_mode=hosted, public_access=False),
        'Request': Request, 'JSONResponse': JSONResponse,
        'InvalidSession': InvalidSession, 'Denied': Denied, 'Overloaded': Overloaded,
        'run_in_threadpool': run_in_threadpool, 'artifact_scope': artifact_scope,
        'COOKIE': 'session',
        'valid_bearer': lambda r: r.headers.get('authorization') == 'Bearer valid',
        'same_origin': lambda r: False,
    }
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), scope)  # noqa: S102 - trusted local AST
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                   and n.name == 'validation_handler')
    handler.decorator_list = []
    handler_module = ast.Module(body=[handler], type_ignores=[])
    exec(compile(ast.fix_missing_locations(handler_module), str(path), 'exec'), scope)  # noqa: S102
    app.add_exception_handler(RequestValidationError, scope['validation_handler'])
    app.middleware('http')(scope['protect_drone_routes'])
    return TestClient(app)


@pytest.mark.parametrize('hosted', [False, True])
def test_actual_middleware_requires_identity_for_stateless_route(hosted):
    client = guarded_client(hosted)
    body = {'model_id': MODEL_ID, 'altitude_m': 20000.0, 'altitude_kind': 'geometric'}
    assert client.post('/api/drone/atmosphere/evaluate', json=body).status_code == 401
    assert client.post('/api/drone/atmosphere/evaluate', json=body,
                       headers={'Authorization':'Bearer invalid'}).status_code == 401
    assert client.post('/api/drone/atmosphere/evaluate', json=body,
                       headers={'Authorization':'Bearer valid'}).status_code == 200
    assert client.post('/api/drone/unscoped-write', json={},
                       headers={'Authorization':'Bearer valid'}).status_code in (403, 404)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
@pytest.mark.parametrize('hosted', [False, True])
def test_nonfinite_validation_error_is_safe_json(value, hosted):
    client = guarded_client(hosted)
    raw = ('{"model_id":"' + MODEL_ID + '","altitude_m":' + value
           + ',"altitude_kind":"geometric"}')
    response = client.post('/api/drone/atmosphere/evaluate', content=raw,
                           headers={'Authorization': 'Bearer valid', 'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid atmosphere request.'}


def test_hosted_trailing_slash_is_explicitly_not_authorized():
    client = guarded_client(True)
    body = {'model_id': MODEL_ID, 'altitude_m': 20000.0, 'altitude_kind': 'geometric'}
    response = client.post('/api/drone/atmosphere/evaluate/', json=body,
                           headers={'Authorization': 'Bearer valid'}, follow_redirects=False)
    assert response.status_code == 403
