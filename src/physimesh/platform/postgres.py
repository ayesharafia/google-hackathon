"""PostgreSQL project adapter preserving immutable local contracts and version checks."""
from physimesh.projects.sqlite import SQLiteProjects

from .database import MetadataDB

PROJECT_DDL = (
    '''CREATE TABLE IF NOT EXISTS project_meta (
        project_id TEXT PRIMARY KEY, title TEXT NOT NULL, version INTEGER NOT NULL,
        snapshot TEXT NOT NULL, created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS design_revisions (
        project_id TEXT NOT NULL REFERENCES project_meta(project_id), draft_version INTEGER NOT NULL,
        purpose TEXT NOT NULL, revision_sha256 TEXT NOT NULL, record BYTEA NOT NULL,
        PRIMARY KEY(project_id,draft_version,purpose), UNIQUE(project_id,revision_sha256))''',
    '''CREATE TABLE IF NOT EXISTS local_studies (
        project_id TEXT NOT NULL REFERENCES project_meta(project_id), revision_sha256 TEXT NOT NULL,
        study_sha256 TEXT NOT NULL, result_sha256 TEXT NOT NULL, created_utc TEXT NOT NULL,
        PRIMARY KEY(project_id,study_sha256))''',
    '''CREATE TABLE IF NOT EXISTS report_cache (
        cache_key TEXT PRIMARY KEY, pdf_sha256 TEXT NOT NULL, receipt TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS project_inventory ON project_meta(updated_utc DESC,project_id)',
    'CREATE INDEX IF NOT EXISTS study_history ON local_studies(project_id,created_utc DESC,study_sha256)',
)


class PostgreSQLProjects(SQLiteProjects):
    def __init__(self, database: MetadataDB):
        if not database.postgres:
            raise ValueError('PostgreSQL adapter requires PostgreSQL')
        self.database = database
        with self._connection(write=True) as db:
            db.execute('SELECT pg_advisory_xact_lock(17010601)')
            db.execute('CREATE TABLE IF NOT EXISTS project_migrations(version INTEGER PRIMARY KEY)')
            versions = [r[0] for r in db.execute('SELECT version FROM project_migrations').fetchall()]
            if any(v != 1 for v in versions):
                raise ValueError('unsupported hosted project migration')
            for sql in PROJECT_DDL:
                db.execute(sql)
            db.execute('INSERT OR IGNORE INTO project_migrations VALUES(1)')

    def _connection(self, *, write=False):
        return self.database.connection(write=write)

    @staticmethod
    def _row(db, project_id):
        from physimesh.projects.repository import ProjectMissing
        # Row locking keeps read-version/update atomic without locking unrelated projects.
        row = db.execute('SELECT * FROM project_meta WHERE project_id=? FOR UPDATE', (project_id,)).fetchone()
        if row is None:
            raise ProjectMissing(project_id)
        return row
