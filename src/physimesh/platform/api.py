"""Private identity and workflow routes. Requests use verified principals only."""
import hashlib
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from physimesh.api.projects import operation
from physimesh.drone.provenance import canonical_json

from .identity import InvalidSession
from .scoped_artifacts import artifact_scope

router = APIRouter(prefix='/api/drone/platform')


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Login(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class Invite(Strict):
    email: str = Field(max_length=254)
    role: Literal['engineer', 'reviewer', 'viewer']
    lifetime_s: int = Field(default=86400, ge=60, le=604800)


class Accept(Strict):
    invitation_token: str = Field(min_length=20, max_length=128)


class Review(Strict):
    study_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    decision: Literal['comment', 'accepted', 'changes_requested']
    comment: str = Field(max_length=10000)


def identity(request):
    value = getattr(request.app.state, 'identity', None)
    if value is None:
        raise HTTPException(404, 'individual identity requires hosted mode')
    return value


@router.post('/login')
def login(request: Request, body: Login):
    try:
        return identity(request).login(body.email, body.password)
    except InvalidSession as exc:
        raise HTTPException(401, str(exc)) from exc


@router.get('/me')
def me(request: Request):
    access = identity(request)
    principal = request.state.principal
    with access.database.connection() as db:
        rows = db.execute('SELECT o.org_id,o.name,m.role FROM organizations o JOIN org_members m '
                          'ON m.org_id=o.org_id WHERE m.user_id=? ORDER BY o.org_id LIMIT 100',
                          (principal.user_id,)).fetchall()
    return {'user_id': principal.user_id, 'email': principal.email, 'organizations': [dict(r) for r in rows]}


@router.post('/logout')
def logout(request: Request, all_sessions: bool = False):
    identity(request).revoke(request.state.principal, all_sessions=all_sessions)
    return {'revoked': True}


@router.post('/projects/{project_id}/invitations', status_code=201)
def invite(request: Request, project_id: str, body: Invite):
    return operation(lambda: identity(request).invite(request.state.principal, project_id, body.email,
                                                     body.role, lifetime_s=body.lifetime_s))


@router.post('/invitations/accept')
def accept(request: Request, body: Accept):
    return operation(lambda: identity(request).accept(request.state.principal, body.invitation_token))


@router.delete('/members/{project_id}/{user_id}')
def remove(request: Request, project_id: str, user_id: str):
    identity(request).remove_member(request.state.principal, project_id, user_id)
    return {'removed': True}


@router.post('/reviews/{project_id}', status_code=201)
def review(request: Request, project_id: str, body: Review):
    access = identity(request)
    access.authorize(request.state.principal, project_id)
    def retain():
        with artifact_scope(project_id):
            request.app.state.studies.read(project_id, body.study_sha256)
        result = request.app.state.projects.repository.study_digest(project_id, body.study_sha256)
        return access.review(request.state.principal, project_id, body.study_sha256,
                             result, body.decision, body.comment)
    return operation(retain)


@router.get('/reviews/{project_id}')
def reviews(request: Request, project_id: str, limit: int = 25, after: str = ''):
    access = identity(request)
    access.authorize(request.state.principal, project_id)
    if not 1 <= limit <= 100 or len(after) > 80:
        raise HTTPException(422, 'invalid review page')
    with access.database.connection() as db:
        rows = db.execute('SELECT r.*,u.email AS author_email FROM reviews r JOIN users u ON u.user_id=r.user_id '
                          'WHERE r.project_id=? AND r.review_id>? ORDER BY r.review_id LIMIT ?', (project_id, after, limit+1)).fetchall()
    return {'reviews': [dict(r) for r in rows[:limit]],
            'next_cursor': rows[limit-1]['review_id'] if len(rows) > limit else None}


@router.get('/reviews/{project_id}/{review_id}/export')
def export_review(request: Request, project_id: str, review_id: str):
    access = identity(request)
    access.authorize(request.state.principal, project_id)
    with access.database.connection() as db:
        row = db.execute('SELECT r.*,u.email AS author_email FROM reviews r JOIN users u ON u.user_id=r.user_id '
                         'WHERE r.project_id=? AND r.review_id=?', (project_id, review_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'review not found')
    raw = canonical_json({'schema_version': 'authenticated_workflow_review_v1', 'review': dict(row),
                          'qualification': 'Workflow review only; not model/aircraft approval.'}).encode()
    return Response(raw, media_type='application/json', headers={
        'Content-Disposition': 'attachment; filename="workflow-review.json"',
        'X-Content-SHA256': hashlib.sha256(raw).hexdigest()})


@router.delete('/invitations/{invitation_id}')
def revoke_invitation(request: Request, invitation_id: str):
    identity(request).revoke_invitation(request.state.principal, invitation_id)
    return {'revoked': True}


@router.get('/sessions')
def sessions(request: Request):
    access = identity(request)
    with access.database.connection() as db:
        rows = db.execute('SELECT token_hash,expires_at,revoked FROM sessions WHERE user_id=? '
                          'ORDER BY expires_at DESC LIMIT 20', (request.state.principal.user_id,)).fetchall()
    return {'sessions': [dict(r) for r in rows]}


@router.delete('/sessions/{session_id}')
def revoke_session(request: Request, session_id: str):
    with identity(request).database.connection(write=True) as db:
        db.execute('UPDATE sessions SET revoked=1 WHERE token_hash=? AND user_id=?',
                   (session_id, request.state.principal.user_id))
    return {'revoked': True}
