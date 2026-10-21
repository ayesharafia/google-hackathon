"""Durable attempts with transactional leases and monotonically increasing fences."""
import json
import time
from uuid import uuid4

from physimesh.drone.provenance import sha256_record

from .database import Overloaded
from .identity import Denied
from .migrations import migrate


class StaleAttempt(Exception):
    pass


class Jobs:
    def __init__(self, database, *, clock=time.time, lease_s=30, queue_limit=256,
                 per_project_limit=8, max_running=4):
        if not 1 <= lease_s <= 300 or min(queue_limit, per_project_limit, max_running) < 1:
            raise ValueError('invalid job limits')
        self.database, self.clock, self.lease_s = database, clock, lease_s
        self.queue_limit, self.per_project_limit, self.max_running = queue_limit, per_project_limit, max_running
        migrate(database)

    def _lock(self, db):
        suffix = ' FOR UPDATE' if self.database.postgres else ''
        db.execute('SELECT quota_id FROM platform_quota WHERE quota_id=1'+suffix).fetchone()

    def submit(self, project_id, kind, spec, *, max_attempts=3, submitted_by=None):
        if kind not in ('study', 'report') or not 1 <= max_attempts <= 5:
            raise ValueError('unsupported job type or retry policy')
        raw = json.dumps(spec, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(raw) > 10000:
            raise ValueError('job specification exceeds budget')
        key = sha256_record(spec)
        with self.database.connection(write=True) as db:
            self._lock(db)
            old = db.execute('SELECT * FROM durable_jobs WHERE project_id=? AND kind=? AND idem_key=?',
                             (project_id, kind, key)).fetchone()
            if old:
                return dict(old)
            if db.execute('SELECT COUNT(*) FROM durable_jobs WHERE project_id=?', (project_id,)).fetchone()[0] >= 10000:
                raise Overloaded('project job history budget exceeded')
            active = "state IN ('queued','running')"
            total = db.execute('SELECT COUNT(*) FROM durable_jobs WHERE '+active).fetchone()[0]
            count = db.execute('SELECT COUNT(*) FROM durable_jobs WHERE project_id=? AND '+active,
                               (project_id,)).fetchone()[0]
            if total >= self.queue_limit or count >= self.per_project_limit:
                raise Overloaded('job queue capacity exceeded; retry later')
            job_id, now = 'job_'+uuid4().hex, self.clock()
            db.execute('INSERT INTO durable_jobs(job_id,project_id,kind,spec_json,idem_key,state,generation,'
                       'attempt_count,max_attempts,created_at,ready_at,submitted_by,build_sha256) '
                       'VALUES(?,?,?,?,?,\'queued\',0,0,?,?,?,?,?)',
                       (job_id, project_id, kind, raw, key, max_attempts, now, now, submitted_by,
                        spec.get('application_build')))
            return dict(db.execute('SELECT * FROM durable_jobs WHERE job_id=?', (job_id,)).fetchone())

    def _recover(self, db, now):
        expired = db.execute("SELECT * FROM durable_jobs WHERE state='running' AND lease_until<=?", (now,)).fetchall()
        for job in expired:
            db.execute("UPDATE execution_attempts SET state='expired',finished_at=?,detail='heartbeat lease expired' "
                       'WHERE job_id=? AND generation=? AND state=\'running\'', (now, job['job_id'], job['generation']))
            state = 'queued' if job['attempt_count'] < job['max_attempts'] else 'failed'
            db.execute('UPDATE durable_jobs SET state=?,worker_id=NULL,lease_until=NULL,ready_at=?,reason=? '
                       'WHERE job_id=?', (state, now, 'worker lease expired', job['job_id']))

    def claim(self, worker_id, *, build_sha256=None):
        if not isinstance(worker_id, str) or not 1 <= len(worker_id) <= 160:
            raise ValueError('worker identity required')
        with self.database.connection(write=True) as db:
            self._lock(db)
            now = self.clock()
            self._recover(db, now)
            if db.execute("SELECT COUNT(*) FROM durable_jobs WHERE state='running'").fetchone()[0] >= self.max_running:
                return None
            job = db.execute("SELECT * FROM durable_jobs WHERE state='queued' AND ready_at<=? "
                             'AND ((build_sha256 IS NULL AND CAST(? AS TEXT) IS NULL) OR build_sha256=?) '
                             'ORDER BY created_at,job_id LIMIT 1', (now, build_sha256, build_sha256)).fetchone()
            if not job:
                return None
            fence, attempt = job['generation']+1, 'attempt_'+uuid4().hex
            db.execute("UPDATE durable_jobs SET state='running',generation=?,attempt_count=attempt_count+1,"
                       'worker_id=?,lease_until=?,reason=NULL WHERE job_id=?',
                       (fence, worker_id, now+self.lease_s, job['job_id']))
            db.execute("INSERT INTO execution_attempts VALUES(?,?,?,?,'running',?,NULL,0,'claimed',NULL,NULL)",
                       (attempt, job['job_id'], fence, worker_id, now))
            return {**dict(job), 'generation': fence, 'worker_id': worker_id,
                    'attempt_id': attempt, 'spec': json.loads(job['spec_json']), 'state': 'running'}

    def _current(self, db, claim):
        self._lock(db)
        job = db.execute('SELECT * FROM durable_jobs WHERE job_id=?', (claim['job_id'],)).fetchone()
        if (job is None or job['state'] != 'running' or job['generation'] != claim['generation']
                or job['worker_id'] != claim['worker_id'] or job['lease_until'] <= self.clock()):
            raise StaleAttempt('lease/fence is no longer current; publication refused')
        return job

    def heartbeat(self, claim, progress=0, detail='running', resources=None):
        if not 0 <= progress <= 1 or len(detail) > 2000:
            raise ValueError('invalid progress')
        with self.database.connection(write=True) as db:
            self._current(db, claim)
            db.execute('UPDATE durable_jobs SET lease_until=? WHERE job_id=?',
                       (self.clock()+self.lease_s, claim['job_id']))
            db.execute('UPDATE execution_attempts SET progress=?,detail=?,resource_json=? WHERE job_id=? AND generation=?',
                       (progress, detail, json.dumps(resources, allow_nan=False) if resources else None,
                        claim['job_id'], claim['generation']))

    def complete(self, claim, result):
        raw = json.dumps(result, sort_keys=True, allow_nan=False)
        if len(raw) > 10000:
            raise ValueError('accepted result receipt exceeds budget')
        with self.database.connection(write=True) as db:
            self._current(db, claim)
            db.execute("UPDATE execution_attempts SET state='accepted',progress=1,result_json=?,finished_at=?,resource_json=? "
                       'WHERE job_id=? AND generation=?', (raw, self.clock(), json.dumps(result.get('resources'), allow_nan=False),
                                                               claim['job_id'], claim['generation']))
            db.execute("UPDATE durable_jobs SET state='succeeded',result_json=?,lease_until=NULL WHERE job_id=?",
                       (raw, claim['job_id']))

    def fail(self, claim, reason, *, retry=True, resources=None):
        with self.database.connection(write=True) as db:
            job = self._current(db, claim)
            now = self.clock()
            state = 'queued' if retry and job['attempt_count'] < job['max_attempts'] else 'failed'
            reason = str(reason)[:2000]
            db.execute("UPDATE execution_attempts SET state='failed',detail=?,finished_at=?,resource_json=COALESCE(?,resource_json) "
                       'WHERE job_id=? AND generation=?', (reason, now, json.dumps(resources, allow_nan=False) if resources else None,
                                                                 claim['job_id'], claim['generation']))
            db.execute('UPDATE durable_jobs SET state=?,reason=?,ready_at=?,lease_until=NULL,worker_id=NULL '
                       'WHERE job_id=?', (state, reason, now+min(60, 2**job['attempt_count']), claim['job_id']))

    def get(self, project_id, job_id):
        with self.database.connection() as db:
            job = db.execute('SELECT * FROM durable_jobs WHERE project_id=? AND job_id=?',
                             (project_id, job_id)).fetchone()
            if job is None:
                raise Denied('job access denied')
            attempts = db.execute('SELECT * FROM execution_attempts WHERE job_id=? ORDER BY generation',
                                  (job_id,)).fetchall()
            return {**dict(job), 'attempts': [dict(row) for row in attempts]}

    def page(self, project_id, *, limit=25, after=''):
        from physimesh.projects.sqlite import decode_cursor, encode_cursor, validate_page
        validate_page(limit)
        condition, args = '', [project_id]
        if after:
            left, right = decode_cursor(after)
            try:
                timestamp = float(left)
            except ValueError as exc:
                raise ValueError('invalid job cursor timestamp') from exc
            condition = ' AND (created_at<? OR (created_at=? AND job_id>?))'
            args.extend((timestamp, timestamp, right))
        with self.database.connection() as db:
            rows = db.execute('SELECT job_id,kind,state,created_at,attempt_count,reason FROM durable_jobs '
                              'WHERE project_id=?'+condition+' ORDER BY created_at DESC,job_id LIMIT ?',
                              (*args, limit+1)).fetchall()
        return {'jobs': [dict(r) for r in rows[:limit]],
                'next_cursor': encode_cursor(str(rows[limit-1]['created_at']), rows[limit-1]['job_id'])
                if len(rows) > limit else None}

    def cancel(self, project_id, job_id):
        with self.database.connection(write=True) as db:
            self._lock(db)
            job = db.execute('SELECT * FROM durable_jobs WHERE project_id=? AND job_id=?',
                             (project_id, job_id)).fetchone()
            if job is None:
                raise Denied('job access denied')
            if job['state'] in ('queued', 'running'):
                db.execute("UPDATE durable_jobs SET state='cancelled',lease_until=NULL WHERE job_id=?", (job_id,))
                db.execute("UPDATE execution_attempts SET state='cancelled',finished_at=?,detail='cancelled' "
                           "WHERE job_id=? AND state='running'", (self.clock(), job_id))
        return self.get(project_id, job_id)

    def retry(self, project_id, job_id):
        with self.database.connection(write=True) as db:
            self._lock(db)
            job = db.execute('SELECT * FROM durable_jobs WHERE project_id=? AND job_id=?',
                             (project_id, job_id)).fetchone()
            if job is None:
                raise Denied('job access denied')
            if job['state'] not in ('failed', 'cancelled') or job['attempt_count'] >= 5:
                raise ValueError('job is not eligible for another attempt')
            active = db.execute("SELECT COUNT(*) FROM durable_jobs WHERE state IN ('queued','running')").fetchone()[0]
            per_project = db.execute("SELECT COUNT(*) FROM durable_jobs WHERE project_id=? "
                                     "AND state IN ('queued','running')", (project_id,)).fetchone()[0]
            if active >= self.queue_limit or per_project >= self.per_project_limit:
                raise Overloaded('job queue capacity exceeded; retry later')
            db.execute("UPDATE durable_jobs SET state='queued',max_attempts=?,ready_at=?,reason=NULL WHERE job_id=?",
                       (min(5, job['attempt_count']+1), self.clock(), job_id))
        return self.get(project_id, job_id)
