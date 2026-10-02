"""SQLite job ledger with enforced lifecycle (plan Task 1.2, states plan §4.2)."""
from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Optional, Set

ALLOWED_TRANSITIONS = {
    "queued": {"preparing", "cancelled"},
    "preparing": {"meshing", "running", "failed", "cancelled"},
    "meshing": {"running", "failed", "cancelled"},
    "running": {"postprocessing", "failed", "cancelled"},
    "postprocessing": {"completed", "failed", "cancelled"},
}
ACTIVE = ("preparing", "meshing", "running", "postprocessing")


@dataclass(frozen=True)
class Budgets:
    cpu_cores: float
    memory_gb: float
    disk_gb: float
    wall_time_s: int
    pids_limit: int

    def __post_init__(self):
        for k, v in asdict(self).items():
            if v is None or not v > 0:
                raise ValueError(f"budget {k} must be supplied and > 0")


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    payload: dict
    budgets: Budgets
    state: str
    reason: Optional[str]
    worker_id: Optional[str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobLedger:
    def __init__(self, db_path: pathlib.Path):
        self.db = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT, payload TEXT,
            budgets TEXT, state TEXT, reason TEXT, worker_id TEXT, created TEXT, updated TEXT)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(job_id TEXT, at TEXT, event TEXT)""")

    def submit(self, kind: str, payload: dict, budgets: Budgets) -> str:
        jid = uuid.uuid4().hex
        self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
                        (jid, kind, json.dumps(payload), json.dumps(asdict(budgets)), "queued",
                         None, None, _now(), _now()))
        return jid

    def claim_next(self, worker_id: str) -> Optional[Job]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            self.db.execute("UPDATE jobs SET state='preparing', worker_id=?, updated=? WHERE id=?",
                            (worker_id, _now(), row[0]))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.get(row[0])

    def transition(self, job_id: str, new_state: str, *, reason: Optional[str] = None) -> None:
        cur = self.get(job_id).state
        if new_state not in ALLOWED_TRANSITIONS.get(cur, set()):
            raise ValueError(f"illegal transition {cur} -> {new_state}")
        self.db.execute("UPDATE jobs SET state=?, reason=?, updated=? WHERE id=?",
                        (new_state, reason, _now(), job_id))

    def append_event(self, job_id: str, event: dict) -> None:
        self.db.execute("INSERT INTO events VALUES(?,?,?)", (job_id, _now(), json.dumps(event)))

    def get(self, job_id: str) -> Job:
        r = self.db.execute("SELECT id,kind,payload,budgets,state,reason,worker_id FROM jobs WHERE id=?",
                            (job_id,)).fetchone()
        if r is None:
            raise KeyError(job_id)
        return Job(r[0], r[1], json.loads(r[2]), Budgets(**json.loads(r[3])), r[4], r[5], r[6])

    def mark_interrupted(self, live_worker_ids: Set[str]) -> List[str]:
        """Orphaned active jobs become failed/interrupted; never auto-resumed (PDF §5)."""
        q = f"SELECT id, worker_id FROM jobs WHERE state IN ({','.join('?' * len(ACTIVE))})"
        out = []
        for jid, wid in self.db.execute(q, ACTIVE).fetchall():
            if wid not in live_worker_ids:
                self.transition(jid, "failed", reason="interrupted")
                out.append(jid)
        return out
