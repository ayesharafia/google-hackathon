"""Project-bound, revocable consent for a verified remote OAuth client."""

import json
import re

from physimesh.platform.identity import Denied, Principal

from .store import uid


class RemoteConsents:
    def __init__(self, agent):
        self.agent = agent
        self.store = agent.store
        with self.store.database.connection(write=True) as db:
            if self.store.database.postgres:
                db.execute("SELECT pg_advisory_xact_lock(17010611)")
            db.execute("CREATE TABLE IF NOT EXISTS remote_consent_schema(version INTEGER PRIMARY KEY)")
            versions = [r[0] for r in db.execute("SELECT version FROM remote_consent_schema").fetchall()]
            if versions not in ([], [1]):
                raise ValueError("unsupported remote consent schema")
            if not versions:
                db.execute("""CREATE TABLE remote_consents (
                    consent_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, parent_session TEXT NOT NULL,
                    client_id TEXT NOT NULL, project_id TEXT NOT NULL, groups_json TEXT NOT NULL,
                    expires DOUBLE PRECISION NOT NULL, revoked INTEGER NOT NULL)""")
                db.execute("CREATE INDEX remote_consents_owner_client ON remote_consents(user_id,client_id)")
                db.execute("""CREATE TABLE remote_grant_bindings (
                    grant_id TEXT PRIMARY KEY, consent_id TEXT NOT NULL, oauth_hash TEXT NOT NULL,
                    UNIQUE(consent_id,oauth_hash))""")
                db.execute("INSERT INTO remote_consent_schema VALUES(1)")
            db.execute("CREATE TABLE IF NOT EXISTS remote_oauth_sessions(token_hash TEXT PRIMARY KEY)")

    def create(self, principal, project_id, client_id, groups, lifetime):
        if not self.agent.app.state.settings.hosted_mode:
            raise Denied("Remote consent requires hosted mode.")
        if not isinstance(principal, Principal) or not principal.session_hash:
            raise Denied("An active individual session is required.")
        if (
            not isinstance(client_id, str)
            or not 1 <= len(client_id) <= 512
            or re.search(r"[\x00-\x20\x7f]", client_id)
        ):
            raise ValueError("Client ID must be an explicit provider-issued identifier.")
        if (
            not isinstance(groups, list)
            or not groups
            or len(groups) != len(set(groups))
            or any(g not in ("read", "propose", "change", "study") for g in groups)
        ):
            raise ValueError("Invalid capability selection.")
        if type(lifetime) is not int or not 60 <= lifetime <= 86400:
            raise ValueError("Consent lifetime must be from one minute to one day.")
        ctx = self.agent.policy.trusted(principal)
        configured_issuer = self.agent.app.state.settings.remote_mcp_issuer
        if configured_issuer:
            with self.store.database.connection() as db:
                identity = db.execute(
                    "SELECT issuer,subject FROM users WHERE user_id=? AND active=1", (principal.user_id,)
                ).fetchone()
            if not identity or identity["issuer"] != configured_issuer or not identity["subject"]:
                raise Denied("Your account must be linked to the configured identity provider.")
        self.agent.policy.authorize(ctx, project_id, write=any(g != "read" for g in groups))
        now = self.store.clock()
        with self.store.database.connection(write=True) as db:
            self.store.lock(db)
            self.agent.policy.check_locked(db, ctx, project_id, write=any(g != "read" for g in groups))
            session = db.execute(
                "SELECT expires_at FROM sessions WHERE token_hash=?", (principal.session_hash,)
            ).fetchone()
            if not session:
                raise Denied("Session is unavailable.")
            if (
                db.execute(
                    "SELECT COUNT(*) FROM remote_consents WHERE user_id=?", (principal.user_id,)
                ).fetchone()[0]
                >= 100
            ):
                raise Denied("Connection history limit reached.")
            if db.execute(
                "SELECT 1 FROM remote_consents WHERE user_id=? AND client_id=? AND revoked=0 AND expires>?",
                (principal.user_id, client_id, now),
            ).fetchone():
                raise Denied("Revoke the existing connection for this client first.")
            consent_id = uid("consent")
            expires = min(now + lifetime, session["expires_at"])
            db.execute(
                "INSERT INTO remote_consents VALUES(?,?,?,?,?,?,?,0)",
                (
                    consent_id,
                    principal.user_id,
                    principal.session_hash,
                    client_id,
                    project_id,
                    json.dumps(groups),
                    expires,
                ),
            )
        return {
            "consent_id": consent_id,
            "project_id": project_id,
            "client_id": client_id,
            "groups": groups,
            "expires": expires,
        }

    def find(self, user_id, client_id):
        with self.store.database.connection() as db:
            rows = db.execute(
                """SELECT c.*,u.email FROM remote_consents c
                JOIN users u ON u.user_id=c.user_id AND u.active=1
                JOIN sessions s ON s.token_hash=c.parent_session AND s.user_id=c.user_id
                WHERE c.user_id=? AND c.client_id=? AND c.revoked=0 AND c.expires>?
                AND s.revoked=0 AND s.expires_at>?""",
                (user_id, client_id, self.store.clock(), self.store.clock()),
            ).fetchall()
        if len(rows) != 1:
            raise Denied("A unique active project consent is required.")
        row = dict(rows[0])
        row["groups"] = json.loads(row.pop("groups_json"))
        principal = Principal(row["user_id"], row["email"], row["parent_session"])
        self.agent.policy.authorize(
            self.agent.policy.trusted(principal),
            row["project_id"],
            write=any(g != "read" for g in row["groups"]),
        )
        return row

    def bind(self, principal, client_id):
        """Bind a verified OAuth session to its previously granted consent."""
        import hashlib

        if not principal.session_hash:
            raise Denied("A verified OAuth session is required.")
        consent = self.find(principal.user_id, client_id)
        now = self.store.clock()
        ctx = self.agent.policy.trusted(principal)
        with self.store.database.connection(write=True) as db:
            self.store.lock(db)
            self.agent.policy.check_locked(
                db, ctx, consent["project_id"], write=any(g != "read" for g in consent["groups"])
            )
            current = db.execute(
                "SELECT * FROM remote_consents WHERE consent_id=? AND revoked=0 AND expires>?",
                (consent["consent_id"], now),
            ).fetchone()
            parent = db.execute(
                "SELECT 1 FROM sessions WHERE token_hash=? AND user_id=? AND revoked=0 AND expires_at>?",
                (consent["parent_session"], principal.user_id, now),
            ).fetchone()
            oauth = db.execute(
                "SELECT expires_at FROM sessions WHERE token_hash=? AND user_id=? AND revoked=0 AND expires_at>?",
                (principal.session_hash, principal.user_id, now),
            ).fetchone()
            if not current or not parent or not oauth:
                raise Denied("Remote authority expired or changed.")
            old = db.execute(
                "SELECT grant_id FROM remote_grant_bindings WHERE consent_id=? AND oauth_hash=?",
                (consent["consent_id"], principal.session_hash),
            ).fetchone()
            if old:
                grant_id = old["grant_id"]
            else:
                if (
                    db.execute(
                        "SELECT COUNT(*) FROM remote_grant_bindings WHERE consent_id=?",
                        (consent["consent_id"],),
                    ).fetchone()[0]
                    >= 200
                ):
                    raise Denied("Remote session history limit reached; create a new connection.")
                grant_id = uid("grant")
                digest = hashlib.sha256(
                    ("remote:" + consent["consent_id"] + ":" + principal.session_hash).encode()
                ).hexdigest()
                db.execute(
                    "INSERT INTO agent_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        grant_id,
                        digest,
                        ctx.actor,
                        principal.session_hash,
                        "remote",
                        consent["project_id"],
                        "Remote OAuth client",
                        json.dumps(consent["groups"]),
                        min(consent["expires"], oauth["expires_at"]),
                        0,
                        0,
                        200,
                    ),
                )
                db.execute(
                    "INSERT INTO remote_grant_bindings VALUES(?,?,?)",
                    (grant_id, consent["consent_id"], principal.session_hash),
                )
        return {"grant_id": grant_id}

    def list_for_project(self, principal, project_id):
        if not isinstance(principal, Principal) or not principal.session_hash:
            raise Denied("An active individual session is required.")
        ctx = self.agent.policy.trusted(principal)
        self.agent.policy.authorize(ctx, project_id)
        with self.store.database.connection() as db:
            self.agent.policy.check_locked(db, ctx, project_id)
            rows = db.execute(
                "SELECT consent_id,client_id,groups_json,expires,revoked FROM remote_consents WHERE user_id=? AND project_id=? ORDER BY expires DESC LIMIT 100",
                (principal.user_id, project_id),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["groups"] = json.loads(item.pop("groups_json"))
            result.append(item)
        return result

    def revoke(self, principal, consent_id):
        if not isinstance(principal, Principal) or not principal.session_hash:
            raise Denied("An active individual session is required.")
        ctx = self.agent.policy.trusted(principal)
        with self.store.database.connection(write=True) as db:
            self.store.lock(db)
            self.agent.policy.check_locked(db, ctx, None)
            db.execute(
                "UPDATE remote_consents SET revoked=1 WHERE consent_id=? AND user_id=?",
                (consent_id, principal.user_id),
            )
        return {"revoked": True}
