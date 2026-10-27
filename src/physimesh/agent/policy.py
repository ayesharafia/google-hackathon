"""Scopes attenuate real user authority; a client label never grants a role."""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass

from physimesh.platform.identity import Denied, Principal

from .store import uid


@dataclass(frozen=True)
class Context:
    actor: str
    principal: Principal | None = None
    grant_id: str | None = None
    project_id: str | None = None
    groups: tuple = ("read", "propose", "change", "study")


class Policy:
    def __init__(self, app, store):
        self.app, self.store = app, store

    def binding(self):
        return hmac.new(
            self.app.state.settings.api_token.encode(), b"physicore-agent-parent-v1", hashlib.sha256
        ).hexdigest()

    def trusted(self, principal=None):
        if self.app.state.settings.public_access:
            raise Denied("Agent access requires an authenticated workspace.")
        if self.app.state.settings.hosted_mode:
            if principal is None:
                raise Denied("Individual session required.")
            return Context("hosted:" + principal.user_id, principal)
        return Context("local:" + self.binding())

    def grant_context(self, *, token=None, grant_id=None):
        if self.app.state.settings.public_access:
            raise Denied("Agent access is disabled in public-access mode.")
        key, value = (
            ("token_hash", hashlib.sha256(token.encode()).hexdigest()) if token else ("grant_id", grant_id)
        )
        with self.store.database.connection() as db:
            row = db.execute("SELECT * FROM agent_grants WHERE " + key + "=?", (value,)).fetchone()
            if row is None or row["revoked"] or row["expires"] <= self.store.clock():
                raise Denied("AI-client grant is missing, expired, revoked or exhausted.")
            row = dict(row)
            remote = db.execute(
                "SELECT consent_id FROM remote_grant_bindings WHERE grant_id=?", (row["grant_id"],)
            ).fetchone()
            if remote:
                valid = db.execute(
                    """SELECT 1 FROM remote_consents c JOIN sessions s ON s.token_hash=c.parent_session
                    AND s.user_id=c.user_id JOIN users u ON u.user_id=c.user_id AND u.active=1
                    WHERE c.consent_id=? AND c.revoked=0 AND c.expires>? AND s.revoked=0 AND s.expires_at>?
                    AND c.project_id=?""",
                    (remote["consent_id"], self.store.clock(), self.store.clock(), row["project_id"]),
                ).fetchone()
                if not valid:
                    raise Denied("Remote project consent is no longer active.")
            principal = None
            if self.app.state.settings.hosted_mode:
                session = db.execute(
                    "SELECT u.user_id,u.email FROM sessions s JOIN users u ON u.user_id=s.user_id "
                    "WHERE s.token_hash=? AND s.revoked=0 AND s.expires_at>? AND u.active=1",
                    (row["parent_session"], self.store.clock()),
                ).fetchone()
                if session is None or row["actor"] != "hosted:" + session["user_id"]:
                    raise Denied("Parent session is no longer active.")
                principal = Principal(session["user_id"], session["email"], row["parent_session"])
            elif not hmac.compare_digest(row["binding"], self.binding()):
                raise Denied("Workspace credential changed; create a new AI-client grant.")
        ctx = Context(
            row["actor"], principal, row["grant_id"], row["project_id"], tuple(json.loads(row["groups_json"]))
        )
        self.authorize(ctx, row["project_id"])
        return ctx

    def refresh(self, ctx):
        return self.grant_context(grant_id=ctx.grant_id) if ctx.grant_id else self.trusted(ctx.principal)

    def authorize(self, ctx, project_id, *, write=False):
        if ctx.grant_id and project_id != ctx.project_id:
            raise Denied("Project is outside this AI-client grant.")
        if self.app.state.settings.hosted_mode:
            self.app.state.identity.authorize(ctx.principal, project_id, write=write)

    def mint(self, ctx, body):
        if ctx.grant_id:
            raise Denied("A trusted user session is required to manage grants.")
        self.authorize(ctx, body.project_id, write=any(g != "read" for g in body.groups))
        self.app.state.projects.repository.get(body.project_id)
        token, grant_id = "pca_" + secrets.token_urlsafe(32), uid("grant")
        expires = self.store.clock() + body.lifetime_s
        if ctx.principal:
            if not ctx.principal.session_hash:
                raise Denied("An expiring individual session is required.")
            with self.store.database.connection() as db:
                row = db.execute(
                    "SELECT expires_at FROM sessions WHERE token_hash=?", (ctx.principal.session_hash,)
                ).fetchone()
                if row is None:
                    raise Denied("Parent session missing.")
                expires = min(expires, row["expires_at"])
        with self.store.database.connection(write=True) as db:
            self.store.lock(db)
            count = db.execute("SELECT COUNT(*) FROM agent_grants WHERE actor=?", (ctx.actor,)).fetchone()[0]
            if count >= 100:
                raise Denied("Client-connection history limit reached.")
            db.execute(
                "INSERT INTO agent_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    grant_id,
                    hashlib.sha256(token.encode()).hexdigest(),
                    ctx.actor,
                    ctx.principal.session_hash if ctx.principal else None,
                    self.binding(),
                    body.project_id,
                    body.name,
                    json.dumps(body.groups),
                    expires,
                    0,
                    0,
                    body.max_calls,
                ),
            )
        return {
            "grant_id": grant_id,
            "token": token,
            "project_id": body.project_id,
            "expires": expires,
            "groups": body.groups,
            "max_calls": body.max_calls,
        }

    def grants(self, ctx):
        if ctx.grant_id:
            raise Denied("A trusted session is required to manage grants.")
        with self.store.database.connection() as db:
            rows = db.execute(
                "SELECT grant_id,project_id,name,groups_json,expires,revoked,calls,max_calls "
                "FROM agent_grants WHERE actor=? ORDER BY expires DESC LIMIT 100",
                (ctx.actor,),
            ).fetchall()
        result = []
        for row in rows:
            try:
                self.authorize(ctx, row["project_id"])
            except Denied:
                continue
            item = dict(row)
            item["groups"] = json.loads(item.pop("groups_json"))
            result.append(item)
        return {"grants": result}

    def revoke(self, ctx, grant_id):
        if ctx.grant_id:
            raise Denied("A trusted session is required to revoke grants.")
        with self.store.database.connection(write=True) as db:
            self.store.lock(db)
            db.execute(
                "UPDATE agent_grants SET revoked=1 WHERE grant_id=? AND actor=?", (grant_id, ctx.actor)
            )
        return {"revoked": True}

    def count_call(self, ctx):
        if ctx.grant_id:
            with self.store.database.connection(write=True) as db:
                self.store.lock(db)
                row = db.execute(
                    "SELECT calls,max_calls,expires,revoked FROM agent_grants WHERE grant_id=?",
                    (ctx.grant_id,),
                ).fetchone()
                if (
                    row is None
                    or row["revoked"]
                    or row["expires"] <= self.store.clock()
                    or row["calls"] >= row["max_calls"]
                ):
                    raise Denied("AI-client grant is no longer usable.")
                db.execute("UPDATE agent_grants SET calls=calls+1 WHERE grant_id=?", (ctx.grant_id,))

    def check_locked(self, db, ctx, project_id, *, write=False):
        """Recheck admission in the mutation transaction; PG locks authority rows."""
        share = " FOR SHARE" if self.store.database.postgres else ""
        if ctx.grant_id:
            row = db.execute("SELECT * FROM agent_grants WHERE grant_id=?", (ctx.grant_id,)).fetchone()
            if (
                row is None
                or row["revoked"]
                or row["expires"] <= self.store.clock()
                or row["actor"] != ctx.actor
                or (project_id and row["project_id"] != project_id)
            ):
                raise Denied("AI-client authority changed before admission.")
            remote = db.execute(
                "SELECT consent_id FROM remote_grant_bindings WHERE grant_id=?", (ctx.grant_id,)
            ).fetchone()
            if remote:
                valid = db.execute(
                    """SELECT c.consent_id FROM remote_consents c JOIN sessions s ON s.token_hash=c.parent_session
                    AND s.user_id=c.user_id JOIN users u ON u.user_id=c.user_id AND u.active=1
                    WHERE c.consent_id=? AND c.revoked=0 AND c.expires>? AND s.revoked=0 AND s.expires_at>?
                    AND c.project_id=?"""
                    + share,
                    (remote["consent_id"], self.store.clock(), self.store.clock(), row["project_id"]),
                ).fetchone()
                if not valid:
                    raise Denied("Remote project consent changed before admission.")
            if not self.app.state.settings.hosted_mode and not hmac.compare_digest(
                row["binding"], self.binding()
            ):
                raise Denied("Workspace credential changed.")
        if not self.app.state.settings.hosted_mode:
            return
        principal = ctx.principal
        session = db.execute(
            "SELECT u.user_id FROM users u JOIN sessions s ON s.user_id=u.user_id "
            "WHERE s.token_hash=? AND s.revoked=0 AND s.expires_at>? AND u.active=1" + share,
            (principal.session_hash, self.store.clock()),
        ).fetchone()
        if session is None or session["user_id"] != principal.user_id:
            raise Denied("Parent session is no longer active.")
        if project_id:
            project = db.execute(
                "SELECT org_id FROM platform_projects WHERE project_id=?", (project_id,)
            ).fetchone()
            if project is None:
                raise Denied("Project access denied.")
            org = db.execute(
                "SELECT role FROM org_members WHERE org_id=? AND user_id=?" + share,
                (project["org_id"], principal.user_id),
            ).fetchone()
            member = db.execute(
                "SELECT role FROM project_members WHERE project_id=? AND user_id=?" + share,
                (project_id, principal.user_id),
            ).fetchone()
            allowed = org and (
                org["role"] == "admin"
                or member
                and member["role"] in (("engineer",) if write else ("engineer", "reviewer", "viewer"))
            )
            if not allowed:
                raise Denied("Project access changed before admission.")
