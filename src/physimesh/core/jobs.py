"""SQLite job ledger with enforced lifecycle (plan Task 1.2, states plan §4.2)."""
from __future__ import annotations

import json
import math
import pathlib
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

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
    """Required limits: cores, memory in Docker g units (GiB), disk GB, seconds, PIDs.

    Memory follows Task 1.2 argv; disk GB is decimal [ASSUMPTION]. [M§26]"""
    cpu_cores: float
    memory_gb: float
    disk_gb: float
    wall_time_s: int
    pids_limit: int

    def __post_init__(self) -> None:
        for k, v in asdict(self).items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                raise ValueError(f"budget {k} must be supplied and > 0")
        for k in ("wall_time_s", "pids_limit"):
            if not isinstance(getattr(self, k), int):
                raise TypeError(f"budget {k} must be an integer")


@dataclass(frozen=True)
class Job:
    """Durable job snapshot; budget units follow Budgets, no aircraft status."""
    id: str
    kind: str
    payload: dict
    budgets: Budgets
    state: str
    reason: str | None
    worker_id: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobLedger:
    """Durable lifecycle ledger; one connection per worker thread [M§26]."""

    def __init__(self, db_path: pathlib.Path) -> None:
        # Wait up to 30 seconds for short competing ledger transactions [ASSUMPTION].
        self.db = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT, payload_json TEXT,
            budgets_json TEXT, state TEXT, reason TEXT, worker_id TEXT, created_utc TEXT, updated_utc TEXT)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(job_id TEXT, at TEXT, event TEXT)""")

    def submit(self, kind: str, payload: dict, budgets: Budgets) -> str:
        """Queue JSON inputs and explicit resource budgets, returning a job ID."""
        jid = uuid.uuid4().hex
        self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
                        (jid, kind, json.dumps(payload), json.dumps(asdict(budgets)), "queued",
                         None, None, _now(), _now()))
        return jid

    def claim_next(self, worker_id: str) -> Job | None:
        """Atomically claim the oldest queued job for a named worker."""
        if not worker_id:
            raise ValueError("worker_id is required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created_utc, id LIMIT 1").fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            self.db.execute("UPDATE jobs SET state='preparing', worker_id=?, updated_utc=? WHERE id=?",
                            (worker_id, _now(), row[0]))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.get(row[0])

    def claim_job(self, job_id: str, worker_id: str) -> Job:
        """Claim one known queued job atomically without taking an unrelated job."""
        if not worker_id:
            raise ValueError("worker_id is required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.get(job_id).state != "queued":
                raise ValueError("job is not queued")
            self.db.execute("UPDATE jobs SET state='preparing', worker_id=?, updated_utc=? WHERE id=?",
                            (worker_id, _now(), job_id))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.get(job_id)

    def transition(self, job_id: str, new_state: str, *, reason: str | None = None) -> None:
        """Apply an allowed transition atomically; execution state only [plan §4.2]."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cur = self.get(job_id).state
            if new_state not in ALLOWED_TRANSITIONS.get(cur, set()):
                raise ValueError(f"illegal transition {cur} -> {new_state}")
            self.db.execute("UPDATE jobs SET state=?, reason=?, updated_utc=? WHERE id=?",
                            (new_state, reason, _now(), job_id))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def append_event(self, job_id: str, event: dict) -> None:
        """Append JSON evidence to an existing job; timestamps are UTC."""
        self.get(job_id)
        self.db.execute("INSERT INTO events VALUES(?,?,?)", (job_id, _now(), json.dumps(event)))

    def get(self, job_id: str) -> Job:
        """Read a job snapshot, raising KeyError if the job does not exist."""
        r = self.db.execute("SELECT id,kind,payload_json,budgets_json,state,reason,worker_id FROM jobs WHERE id=?",
                            (job_id,)).fetchone()
        if r is None:
            raise KeyError(job_id)
        return Job(r[0], r[1], json.loads(r[2]), Budgets(**json.loads(r[3])), r[4], r[5], r[6])

    def mark_interrupted(self, live_worker_ids: set[str]) -> list[str]:
        """Orphaned active jobs become failed/interrupted; never auto-resumed (PDF §5)."""
        q = f"SELECT id, worker_id FROM jobs WHERE state IN ({','.join('?' * len(ACTIVE))})"
        self.db.execute("BEGIN IMMEDIATE")
        try:
            out = []
            for jid, wid in self.db.execute(q, ACTIVE).fetchall():
                if wid not in live_worker_ids:
                    self.db.execute(
                        "UPDATE jobs SET state='failed', reason='interrupted', updated_utc=? WHERE id=?",
                        (_now(), jid),
                    )
                    out.append(jid)
            self.db.execute("COMMIT")
            return out
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
