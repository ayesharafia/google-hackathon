"""Portable independent migration and bounded durable action records."""

import json
import time
from uuid import uuid4

from physimesh.drone.provenance import canonical_json, sha256_record
from physimesh.platform.database import Overloaded

DDL = (
    "CREATE TABLE IF NOT EXISTS agent_schema(version INTEGER PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS agent_lock(lock_id INTEGER PRIMARY KEY)",
    """CREATE TABLE agent_grants(grant_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL UNIQUE,
       actor TEXT NOT NULL,parent_session TEXT,binding TEXT NOT NULL,project_id TEXT NOT NULL,
       name TEXT NOT NULL,groups_json TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL,
       revoked INTEGER NOT NULL,calls INTEGER NOT NULL,max_calls INTEGER NOT NULL)""",
    """CREATE TABLE agent_proposals(proposal_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,actor TEXT NOT NULL,
       before_json TEXT NOT NULL,after_json TEXT NOT NULL,expected_version INTEGER NOT NULL,
       expires DOUBLE PRECISION NOT NULL,changes_json TEXT NOT NULL,applied_version INTEGER,
       applied_hash TEXT,undo_version INTEGER)""",
    """CREATE TABLE agent_reviews(review_id TEXT PRIMARY KEY,actor TEXT NOT NULL,grant_id TEXT,
       project_id TEXT NOT NULL,action TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,
       args_json TEXT NOT NULL,preview_json TEXT NOT NULL,status TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL,
       UNIQUE(actor,request_id))""",
    """CREATE TABLE agent_calls(receipt_id TEXT PRIMARY KEY,actor TEXT NOT NULL,grant_id TEXT,
       project_id TEXT,action TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,
       state TEXT NOT NULL,result_json TEXT,reason TEXT,created DOUBLE PRECISION NOT NULL,
       UNIQUE(actor,request_id))""",
    "CREATE INDEX agent_review_owner ON agent_reviews(actor,project_id,expires)",
    "CREATE INDEX agent_call_project ON agent_calls(project_id,created,receipt_id)",
)


def uid(prefix):
    return prefix + "_" + uuid4().hex


def encoded(value):
    raw = canonical_json(value)
    if len(raw.encode()) > 262144:
        raise ValueError("inline response exceeds 256 KiB; use a bounded resource or export handle")
    return raw


class Store:
    def __init__(self, database, clock=time.time):
        self.database, self.clock = database, clock
        with database.connection(write=True) as db:
            if database.postgres:
                db.execute("SELECT pg_advisory_xact_lock(17010610)")
            db.execute(DDL[0])
            versions = [r[0] for r in db.execute("SELECT version FROM agent_schema").fetchall()]
            if versions not in ([], [1]):
                raise ValueError("unsupported agent schema version")
            if not versions:
                for sql in DDL[1:]:
                    db.execute(sql)
                db.execute("INSERT INTO agent_lock VALUES(1)")
                db.execute("INSERT INTO agent_schema VALUES(1)")

    def lock(self, db):
        db.execute(
            "SELECT lock_id FROM agent_lock WHERE lock_id=1"
            + (" FOR UPDATE" if self.database.postgres else "")
        ).fetchone()

    def quota(self, db, table, project_id, extra=0, *, new_record=True):
        columns = {
            "agent_calls": ("result_json",),
            "agent_proposals": ("before_json", "after_json", "changes_json"),
            "agent_reviews": ("args_json", "preview_json"),
        }
        if table not in columns:
            raise ValueError("unknown metadata budget")
        where, args = ("project_id=?", (project_id,)) if project_id else ("project_id IS NULL", ())
        if (
            new_record
            and db.execute("SELECT COUNT(*) FROM " + table + " WHERE " + where, args).fetchone()[0] >= 10000
        ):
            raise Overloaded("agent record budget exceeded for this project")
        sizes = [
            "COALESCE("
            + (
                "OCTET_LENGTH(" + column + ")"
                if self.database.postgres
                else "LENGTH(CAST(" + column + " AS BLOB))"
            )
            + ",0)"
            for column in columns[table]
        ]
        used = db.execute(
            "SELECT COALESCE(SUM(" + "+".join(sizes) + "),0) FROM " + table + " WHERE " + where, args
        ).fetchone()[0]
        if used + extra > 64_000_000:
            raise Overloaded("agent evidence byte budget exceeded for this project")

    @staticmethod
    def fingerprint(ctx, action, arguments):
        return sha256_record(
            {"actor": ctx.actor, "grant_id": ctx.grant_id, "action": action, "arguments": arguments}
        )

    @staticmethod
    def decode(row, key):
        return json.loads(row[key]) if row[key] is not None else None
