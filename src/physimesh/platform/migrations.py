"""Ordered transactional platform migrations. Unknown newer versions fail closed."""
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS platform_migrations(version INTEGER PRIMARY KEY)',
    '''CREATE TABLE IF NOT EXISTS organizations (
        org_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password TEXT,
        issuer TEXT, subject TEXT, active INTEGER NOT NULL, UNIQUE(issuer,subject))''',
    '''CREATE TABLE IF NOT EXISTS org_members (
        org_id TEXT NOT NULL REFERENCES organizations(org_id), user_id TEXT NOT NULL REFERENCES users(user_id),
        role TEXT NOT NULL CHECK(role IN ('admin','member')), PRIMARY KEY(org_id,user_id))''',
    '''CREATE TABLE IF NOT EXISTS platform_projects (
        project_id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(org_id))''',
    '''CREATE TABLE IF NOT EXISTS project_members (
        project_id TEXT NOT NULL REFERENCES platform_projects(project_id),
        user_id TEXT NOT NULL REFERENCES users(user_id),
        role TEXT NOT NULL CHECK(role IN ('engineer','reviewer','viewer')), PRIMARY KEY(project_id,user_id))''',
    '''CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id),
        expires_at DOUBLE PRECISION NOT NULL, revoked INTEGER NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS login_failures (
        email TEXT PRIMARY KEY, failures INTEGER NOT NULL, retry_at DOUBLE PRECISION NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS invitations (
        token_hash TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES platform_projects(project_id),
        email TEXT NOT NULL, role TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL,
        created_by TEXT NOT NULL REFERENCES users(user_id), accepted_by TEXT)''',
    '''CREATE TABLE IF NOT EXISTS artifact_access (
        project_id TEXT NOT NULL REFERENCES platform_projects(project_id), digest TEXT NOT NULL,
        size_bytes INTEGER NOT NULL, PRIMARY KEY(project_id,digest))''',
    '''CREATE TABLE IF NOT EXISTS reviews (
        review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES platform_projects(project_id),
        study_sha256 TEXT NOT NULL, result_sha256 TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(user_id),
        decision TEXT NOT NULL, comment TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS platform_quota (quota_id INTEGER PRIMARY KEY, artifact_bytes BIGINT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS durable_jobs (
        job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES platform_projects(project_id),
        kind TEXT NOT NULL CHECK(kind IN ('study','report')), spec_json TEXT NOT NULL, idem_key TEXT NOT NULL,
        state TEXT NOT NULL, generation INTEGER NOT NULL, attempt_count INTEGER NOT NULL,
        max_attempts INTEGER NOT NULL, created_at DOUBLE PRECISION NOT NULL,
        ready_at DOUBLE PRECISION NOT NULL, lease_until DOUBLE PRECISION, worker_id TEXT,
        result_json TEXT, reason TEXT, submitted_by TEXT REFERENCES users(user_id), UNIQUE(project_id,kind,idem_key))''',
    '''CREATE TABLE IF NOT EXISTS execution_attempts (
        attempt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES durable_jobs(job_id), generation INTEGER NOT NULL,
        worker_id TEXT NOT NULL, state TEXT NOT NULL, started_at DOUBLE PRECISION NOT NULL,
        finished_at DOUBLE PRECISION, progress DOUBLE PRECISION NOT NULL,
        detail TEXT NOT NULL, result_json TEXT, UNIQUE(job_id,generation))''',
    'CREATE INDEX IF NOT EXISTS job_dispatch ON durable_jobs(state,ready_at,created_at,job_id)',
    'CREATE INDEX IF NOT EXISTS platform_session_user_idx ON sessions(user_id,expires_at)',
    'CREATE INDEX IF NOT EXISTS project_org ON platform_projects(org_id,project_id)',
    'CREATE INDEX IF NOT EXISTS review_project ON reviews(project_id,created_at,review_id)',
)


def migrate(database):
    with database.connection(write=True) as db:
        if database.postgres:
            db.execute('SELECT pg_advisory_xact_lock(17010602)')
        db.execute(SCHEMA[0])
        versions = [r[0] for r in db.execute('SELECT version FROM platform_migrations').fetchall()]
        if sorted(versions) not in ([], [1], [1, 2], [1, 2, 3], [1, 2, 3, 4], [1, 2, 3, 4, 5]):
            raise ValueError('unsupported platform migration; upgrade or restore the matching release')
        if 5 in versions:
            return
        for statement in SCHEMA[1:]:
            db.execute(statement)
        db.execute('INSERT OR IGNORE INTO platform_quota VALUES(1,0)')
        db.execute('INSERT OR IGNORE INTO platform_migrations VALUES(1)')
        if 2 not in versions:
            db.execute('ALTER TABLE execution_attempts ADD COLUMN resource_json TEXT')
            db.execute('INSERT INTO platform_migrations VALUES(2)')
        if 3 not in versions:
            db.execute('ALTER TABLE durable_jobs ADD COLUMN build_sha256 TEXT')
            db.execute('INSERT INTO platform_migrations VALUES(3)')
        db.execute('CREATE INDEX IF NOT EXISTS member_org_lookup ON org_members(user_id,org_id)')
        db.execute('CREATE INDEX IF NOT EXISTS member_project_lookup ON project_members(user_id,project_id)')
        if 4 not in versions:
            db.execute('INSERT INTO platform_migrations VALUES(4)')
        db.execute('CREATE TABLE project_reservations (reservation_id TEXT PRIMARY KEY, '
                   'org_id TEXT NOT NULL REFERENCES organizations(org_id),expires_at DOUBLE PRECISION NOT NULL)')
        db.execute('INSERT INTO platform_migrations VALUES(5)')
