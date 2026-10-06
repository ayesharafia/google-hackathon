"""Request/worker project scopes: a digest is an identity, never an entitlement."""
import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from .identity import Denied


@dataclass
class ArtifactScope:
    project_id: str | None = None
    pending: dict = field(default_factory=dict)


CURRENT_SCOPE = ContextVar('physimesh_artifact_scope', default=None)


@contextmanager
def artifact_scope(project_id=None):
    scope = ArtifactScope(project_id)
    token = CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        CURRENT_SCOPE.reset(token)


class ScopedArtifacts:
    def __init__(self, store, identity):
        self.store, self.identity = store, identity

    def _scope(self):
        scope = CURRENT_SCOPE.get()
        if scope is None:
            raise Denied('an authorized project scope is required')
        return scope

    def _read(self, digest):
        scope = self._scope()
        if digest in scope.pending:
            return
        if not scope.project_id:
            raise Denied('an authorized project scope is required')
        self.identity.require_artifact(scope.project_id, digest)

    def put_bytes(self, data, *, kind, meta):
        scope = self._scope()
        digest = hashlib.sha256(data).hexdigest()
        # Allocate entitlement before writes so over-budget uploads never store bytes.
        if scope.project_id:
            self.identity.grant_artifact(scope.project_id, digest, len(data))
        digest = self.store.put_bytes(data, kind=kind, meta=meta)
        scope.pending[digest] = len(data)
        return digest

    def put_file(self, path, *, kind, meta):
        with open(path, 'rb') as stream:
            data = stream.read(50_000_001)
        if len(data) > 50_000_000:
            raise ValueError('artifact byte budget exceeded')
        return self.put_bytes(data, kind=kind, meta=meta)

    def open(self, digest):
        self._read(digest)
        return self.store.open(digest)

    def meta(self, digest):
        self._read(digest)
        return self.store.meta(digest)

    def bind_pending(self, scope, project_id):
        for digest, size in scope.pending.items():
            self.identity.grant_artifact(project_id, digest, size)

