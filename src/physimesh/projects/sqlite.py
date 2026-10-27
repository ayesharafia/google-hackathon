"""Local transactional drafts and immutable revision bytes; separate from jobs."""
from __future__ import annotations

import base64
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from physimesh.platform.database import Overloaded

from .contracts import DesignRevisionV1, parse_snapshot, snapshot_json
from .repository import DraftConflict, ProjectMissing
from .serialization import dump_contract, load_contract


def utc_now() -> str:
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


class SQLiteProjects:
    """Every operation has its own connection; writes use a bounded exclusive claim."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise ValueError('unsupported local project database version; migration required')
            if version == 3:
                return
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS project_meta (
                    project_id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    version INTEGER NOT NULL, snapshot TEXT NOT NULL,
                    created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS design_revisions (
                    project_id TEXT NOT NULL REFERENCES project_meta(project_id),
                    draft_version INTEGER NOT NULL, purpose TEXT NOT NULL,
                    revision_sha256 TEXT NOT NULL, record BLOB NOT NULL,
                    PRIMARY KEY(project_id, draft_version, purpose),
                    UNIQUE(project_id, revision_sha256)
                );
                CREATE TABLE IF NOT EXISTS local_studies (
                    project_id TEXT NOT NULL REFERENCES project_meta(project_id),
                    revision_sha256 TEXT NOT NULL, study_sha256 TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL, created_utc TEXT NOT NULL,
                    PRIMARY KEY(project_id, study_sha256)
                );
                CREATE TABLE IF NOT EXISTS report_cache (
                    cache_key TEXT PRIMARY KEY, pdf_sha256 TEXT NOT NULL, receipt TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS project_inventory ON project_meta(updated_utc DESC,project_id);
                CREATE INDEX IF NOT EXISTS study_history ON local_studies(project_id,created_utc DESC,study_sha256);
                PRAGMA user_version=3;
            ''')

    @contextmanager
    def _connection(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except sqlite3.OperationalError as exc:
            if write:
                db.rollback()
            if 'locked' in str(exc) or 'busy' in str(exc):
                raise Overloaded('local metadata is busy; retry later') from exc
            raise
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _row(db, project_id):
        row = db.execute('SELECT * FROM project_meta WHERE project_id=?', (project_id,)).fetchone()
        if row is None:
            raise ProjectMissing(project_id)
        return row

    @staticmethod
    def _view(db, row):
        revisions = db.execute(
            'SELECT draft_version,purpose,revision_sha256 FROM design_revisions '
            'WHERE project_id=? ORDER BY draft_version DESC,purpose LIMIT 26', (row['project_id'],)).fetchall()
        studies = db.execute('SELECT revision_sha256,study_sha256,result_sha256,created_utc '
                             'FROM local_studies WHERE project_id=? ORDER BY created_utc DESC,study_sha256 LIMIT 26',
                             (row['project_id'],)).fetchall()
        return {'project_id': row['project_id'], 'title': row['title'], 'studies': [dict(s) for s in studies[:25]],
                'studies_more': len(studies) > 25, 'revisions_more': len(revisions) > 25,
                'draft_version': row['version'], 'snapshot_json': row['snapshot'],
                'created_utc': row['created_utc'], 'updated_utc': row['updated_utc'],
                'revisions': [dict(r) for r in revisions[:25]],
                'access_scope': 'local_single_operator'}

    def create(self, title: str, snapshot: str) -> dict:
        parse_snapshot(snapshot)
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
            raise ValueError('title must contain 1-160 characters')
        project_id = 'project_' + uuid4().hex
        now = utc_now()
        with self._connection(write=True) as db:
            db.execute('INSERT INTO project_meta VALUES(?,?,?,?,?,?)',
                       (project_id, title.strip(), 0, snapshot, now, now))
            row = dict(self._row(db, project_id))
        with self._connection() as db:
            return self._view(db, row)

    def list_projects(self) -> list[dict]:
        """Compatibility list is bounded; inventory clients should follow page cursors."""
        return self.page()['projects']

    def page(self, *, limit=25, after='', user_id=None, organization_id=None) -> dict:
        validate_page(limit)
        if organization_id is not None and user_id is None:
            raise ValueError('organization inventory requires an authenticated identity')
        args, where = [], []
        tables = 'project_meta p'
        if user_id is not None:
            tables += (' JOIN platform_projects pp ON pp.project_id=p.project_id '
                       'JOIN org_members om ON om.org_id=pp.org_id AND om.user_id=? '
                       'LEFT JOIN project_members pm ON pm.project_id=p.project_id AND pm.user_id=om.user_id')
            where.append("(om.role='admin' OR pm.role IS NOT NULL)")
            args.append(user_id)
            if organization_id is not None:
                where.append('pp.org_id=?')
                args.append(organization_id)
        if after:
            updated, project = decode_cursor(after)
            where.append('(p.updated_utc<? OR (p.updated_utc=? AND p.project_id>?))')
            args.extend((updated, updated, project))
        condition = ' WHERE '+' AND '.join(where) if where else ''
        with self._connection() as db:
            rows = db.execute('SELECT p.project_id,p.title,p.version AS draft_version,p.created_utc,p.updated_utc '
                              'FROM '+tables+condition+' ORDER BY p.updated_utc DESC,p.project_id LIMIT ?',
                              (*args, limit+1)).fetchall()
        return {'projects': [dict(r) for r in rows[:limit]],
                'next_cursor': encode_cursor(rows[limit-1]['updated_utc'], rows[limit-1]['project_id'])
                if len(rows) > limit else None}

    def history(self, project_id, kind, *, limit=25, after=''):
        validate_page(limit)
        if kind == 'revisions':
            table, fields, order, first, second = ('design_revisions',
                'draft_version,purpose,revision_sha256', 'draft_version DESC,purpose', 'draft_version', 'purpose')
        elif kind == 'studies':
            table, fields, order, first, second = ('local_studies',
                'revision_sha256,study_sha256,result_sha256,created_utc',
                'created_utc DESC,study_sha256', 'created_utc', 'study_sha256')
        else:
            raise ValueError('unsupported history kind')
        condition, args = '', [project_id]
        if after:
            left, right = decode_cursor(after, integer=kind == 'revisions')
            condition = f' AND ({first}<? OR ({first}=? AND {second}>?))'
            args.extend((left, left, right))
        with self._connection() as db:
            self._row(db, project_id)
            rows = db.execute(f'SELECT {fields} FROM {table} WHERE project_id=?'+condition+
                              f' ORDER BY {order} LIMIT ?', (*args, limit+1)).fetchall()
        return {kind: [dict(r) for r in rows[:limit]],
                'next_cursor': encode_cursor(rows[limit-1][first], rows[limit-1][second])
                if len(rows) > limit else None}

    def report_receipt(self, key):
        with self._connection() as db:
            row = db.execute('SELECT pdf_sha256,receipt FROM report_cache WHERE cache_key=?', (key,)).fetchone()
            return dict(row) if row else None

    def retain_report(self, key, digest, receipt):
        raw = json.dumps(receipt, sort_keys=True, allow_nan=False)
        with self._connection(write=True) as db:
            db.execute('INSERT OR IGNORE INTO report_cache VALUES(?,?,?)', (key, digest, raw))
            return dict(db.execute('SELECT pdf_sha256,receipt FROM report_cache WHERE cache_key=?', (key,)).fetchone())

    def get(self, project_id: str) -> dict:
        with self._connection() as db:
            return self._view(db, self._row(db, project_id))

    def save(self, project_id: str, expected_version: int, snapshot: str) -> dict:
        with self._connection(write=True) as db:
            return self.save_in_transaction(db, project_id, expected_version, snapshot)

    def save_in_transaction(self, db, project_id: str, expected_version: int, snapshot: str) -> dict:
        """Caller owns the transaction, allowing a draft and its action receipt to commit together."""
        parse_snapshot(snapshot)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('expected_version must be a nonnegative integer')
        row = self._row(db, project_id)
        if row['version'] != expected_version:
            raise DraftConflict(row['version'])
        db.execute('UPDATE project_meta SET snapshot=?,version=version+1,updated_utc=? WHERE project_id=?',
                   (snapshot, utc_now(), project_id))
        return self._view(db, self._row(db, project_id))

    def freeze(self, project_id: str, expected_version: int, revision: DesignRevisionV1) -> dict:
        raw = dump_contract(revision)
        if revision.project_id != project_id or revision.approval != 'draft':
            raise ValueError('local freeze must be a same-project draft revision')
        with self._connection(write=True) as db:
            row = self._row(db, project_id)
            if row['version'] != expected_version:
                raise DraftConflict(row['version'])
            if revision.snapshot_json != row['snapshot']:
                raise ValueError('revision must bind the persisted draft')
            old = db.execute('SELECT revision_sha256,record FROM design_revisions '
                             'WHERE project_id=? AND draft_version=? AND purpose=?',
                             (project_id, expected_version, revision.readiness_purpose)).fetchone()
            if old is None:
                retained_bytes = db.execute('SELECT COALESCE(SUM(LENGTH(record)),0) FROM design_revisions '
                                            'WHERE project_id=?', (project_id,)).fetchone()[0]
                if retained_bytes+len(raw) > 250_000_000:
                    raise Overloaded('project revision byte budget exceeded')
                digest = revision.revision_sha256()
                db.execute('INSERT INTO design_revisions VALUES(?,?,?,?,?)',
                           (project_id, expected_version, revision.readiness_purpose, digest, raw))
            else:
                digest, raw = old['revision_sha256'], old['record']
                retained = load_contract(raw)
                if retained.revision_sha256() != digest or retained.snapshot_json != row['snapshot']:
                    raise ValueError('retained revision integrity check failed')
            return {'revision_sha256': digest, 'revision': json.loads(raw),
                    'draft_version': expected_version, 'qualification': 'Local freeze; engineering approval pending.'}

    def revision(self, project_id: str, digest: str) -> DesignRevisionV1:
        with self._connection() as db:
            row = db.execute('SELECT record FROM design_revisions WHERE project_id=? AND revision_sha256=?',
                             (project_id, digest)).fetchone()
            if row is None:
                raise ProjectMissing(digest)
            revision = load_contract(row['record'])
            if not isinstance(revision, DesignRevisionV1) or revision.revision_sha256() != digest:
                raise ValueError('stored revision integrity check failed')
            return revision

    def retain_study(self, project_id: str, revision: str, study: str, result: str) -> str:
        with self._connection(write=True) as db:
            if db.execute('SELECT 1 FROM design_revisions WHERE project_id=? AND revision_sha256=?',
                          (project_id, revision)).fetchone() is None:
                raise ProjectMissing(revision)
            if db.execute('SELECT COUNT(*) FROM local_studies WHERE project_id=?', (project_id,)).fetchone()[0] >= 2000:
                existing = db.execute('SELECT result_sha256 FROM local_studies WHERE project_id=? AND study_sha256=?',
                                      (project_id, study)).fetchone()
                if existing:
                    return existing[0]
                raise Overloaded('project study history budget exceeded')
            db.execute('INSERT OR IGNORE INTO local_studies VALUES(?,?,?,?,?)',
                       (project_id, revision, study, result, utc_now()))
            return db.execute('SELECT result_sha256 FROM local_studies WHERE project_id=? AND study_sha256=?',
                              (project_id, study)).fetchone()[0]

    def study_digest(self, project_id: str, study: str) -> str:
        with self._connection() as db:
            row = db.execute('SELECT result_sha256 FROM local_studies WHERE project_id=? AND study_sha256=?',
                             (project_id, study)).fetchone()
            if row is None:
                raise ProjectMissing(study)
            return row[0]


def canonical_snapshot(raw: str) -> str:
    """Accept JSON text, reject duplicate keys/nonfinite values, canonicalize once."""
    from .contracts import _constant, _pairs
    return snapshot_json(json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant))


def validate_page(limit):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('page limit must be 1–100')


def encode_cursor(left, right):
    return base64.urlsafe_b64encode(json.dumps([left, right], separators=(',', ':')).encode()).decode()


def decode_cursor(cursor, *, integer=False):
    try:
        if not isinstance(cursor, str) or len(cursor) > 512:
            raise ValueError('invalid cursor')
        values = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
        if (not isinstance(values, list) or len(values) != 2 or not isinstance(values[1], str)
                or (type(values[0]) is not int if integer else not isinstance(values[0], str))):
            raise ValueError('invalid cursor')
        return values
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError('invalid page cursor') from exc
