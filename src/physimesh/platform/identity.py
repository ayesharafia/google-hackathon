"""Provider-neutral identities, individual sessions and explicit project entitlements."""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from uuid import uuid4

from .database import Overloaded
from .migrations import migrate


class Denied(Exception):
    pass


class InvalidSession(Exception):
    pass


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError('password must contain 12–1024 characters')
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt+':'+digest


def ident(prefix):
    return prefix+'_'+uuid4().hex


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    session_hash: str | None = None


class Identity:
    def __init__(self, database, *, clock=time.time):
        self.database, self.clock = database, clock
        migrate(database)
        self.dummy = password_hash(secrets.token_urlsafe(24))

    def provision(self, email, *, password=None, issuer=None, subject=None):
        """Administrative provisioning only; JWT subject binding is never client-controlled."""
        email = email.strip().lower()
        if not email or len(email) > 254 or '@' not in email:
            raise ValueError('an individual email identity is required')
        if (password is None) == (issuer is None or subject is None):
            raise ValueError('select password or explicit OIDC issuer and subject')
        user_id = ident('user')
        with self.database.connection(write=True) as db:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,1)',
                       (user_id, email, password_hash(password) if password else None, issuer, subject))
        return user_id

    def organization(self, user_id, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
            raise ValueError('organization name must contain 1–160 characters')
        org = ident('org')
        with self.database.connection(write=True) as db:
            db.execute('INSERT INTO organizations VALUES(?,?,?)', (org, name.strip(), self.clock()))
            db.execute('INSERT INTO org_members VALUES(?,?,?)', (org, user_id, 'admin'))
        return org

    def login(self, email, password):
        email = email.strip().lower()
        with self.database.connection() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            failure = db.execute('SELECT * FROM login_failures WHERE email=?', (email,)).fetchone()
        if failure and failure['retry_at'] > self.clock():
            raise InvalidSession('login temporarily throttled')
        retained = row['password'] if row and row['password'] else self.dummy
        try:
            calculated = password_hash(password, retained.split(':')[0])
        except ValueError:
            calculated = ''
        if not row or not row['active'] or not row['password'] or not hmac.compare_digest(calculated, retained):
            if row:
                with self.database.connection(write=True) as db:
                    current = db.execute('SELECT failures FROM login_failures WHERE email=?', (email,)).fetchone()
                    n = min(10, (current['failures'] if current else 0)+1)
                    db.execute('INSERT INTO login_failures VALUES(?,?,?) ON CONFLICT(email) DO UPDATE '
                               'SET failures=excluded.failures,retry_at=excluded.retry_at',
                               (email, n, self.clock()+min(300, 2**n)))
            raise InvalidSession('invalid credentials')
        token = secrets.token_urlsafe(32)
        with self.database.connection(write=True) as db:
            lock = ' FOR UPDATE' if self.database.postgres else ''
            current = db.execute('SELECT active FROM users WHERE user_id=?'+lock, (row['user_id'],)).fetchone()
            if not current or not current['active']:
                raise InvalidSession('identity is disabled')
            db.execute('DELETE FROM login_failures WHERE email=?', (email,))
            db.execute('DELETE FROM sessions WHERE user_id=? AND (expires_at<=? OR revoked=1)',
                       (row['user_id'], self.clock()))
            if db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?', (row['user_id'],)).fetchone()[0] >= 20:
                raise InvalidSession('session limit reached; revoke an existing session')
            db.execute('INSERT INTO sessions VALUES(?,?,?,0)',
                       (token_hash(token), row['user_id'], self.clock()+43200))
        return {'token': token, 'expires_in_s': 43200, 'user_id': row['user_id']}

    def session(self, token):
        digest = token_hash(token)
        with self.database.connection() as db:
            row = db.execute('SELECT u.user_id,u.email FROM sessions s JOIN users u ON u.user_id=s.user_id '
                             'WHERE s.token_hash=? AND s.revoked=0 AND s.expires_at>? AND u.active=1',
                             (digest, self.clock())).fetchone()
        if row is None:
            raise InvalidSession('missing, revoked or expired session')
        return Principal(row['user_id'], row['email'], digest)

    def oidc(self, claims):
        with self.database.connection() as db:
            row = db.execute('SELECT user_id,email FROM users WHERE issuer=? AND subject=? AND active=1',
                             (claims['iss'], claims['sub'])).fetchone()
        if row is None:
            raise InvalidSession('OIDC identity is not provisioned')
        return Principal(row['user_id'], row['email'])

    def oidc_session(self, token, claims):
        principal = self.oidc(claims)
        digest, now = token_hash(token), self.clock()
        with self.database.connection(write=True) as db:
            lock = ' FOR UPDATE' if self.database.postgres else ''
            user = db.execute('SELECT active FROM users WHERE user_id=?'+lock, (principal.user_id,)).fetchone()
            if not user or not user['active']:
                raise InvalidSession('OIDC identity is disabled')
            old = db.execute('SELECT * FROM sessions WHERE token_hash=?', (digest,)).fetchone()
            if old:
                if old['revoked'] or old['expires_at'] <= now or old['user_id'] != principal.user_id:
                    raise InvalidSession('OIDC session is revoked or expired')
            else:
                db.execute('DELETE FROM sessions WHERE user_id=? AND expires_at<=?', (principal.user_id, now))
                active = db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=? AND revoked=0',
                                    (principal.user_id,)).fetchone()[0]
                total = db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?', (principal.user_id,)).fetchone()[0]
                if active >= 20 or total >= 200:
                    raise InvalidSession('OIDC session budget exceeded')
                expires = min(float(claims['exp']), now+43200)
                if expires <= now:
                    raise InvalidSession('OIDC access token expired')
                db.execute('INSERT INTO sessions VALUES(?,?,?,0)', (digest, principal.user_id, expires))
        return Principal(principal.user_id, principal.email, digest)

    def revoke(self, principal, *, all_sessions=False):
        with self.database.connection(write=True) as db:
            if all_sessions:
                db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (principal.user_id,))
            elif principal.session_hash:
                db.execute('UPDATE sessions SET revoked=1 WHERE token_hash=? AND user_id=?',
                           (principal.session_hash, principal.user_id))
            else:
                raise ValueError('OIDC token revocation belongs to the identity provider')

    def require_admin(self, principal, org_id):
        with self.database.connection() as db:
            row = db.execute("SELECT 1 FROM org_members WHERE org_id=? AND user_id=? AND role='admin'",
                             (org_id, principal.user_id)).fetchone()
        if row is None:
            raise Denied('organization administrator required')

    def reserve_project(self, principal, org_id):
        self.require_admin(principal, org_id)
        reservation = ident('reservation')
        with self.database.connection(write=True) as db:
            suffix = ' FOR UPDATE' if self.database.postgres else ''
            db.execute('SELECT org_id FROM organizations WHERE org_id=?'+suffix, (org_id,)).fetchone()
            db.execute('DELETE FROM project_reservations WHERE org_id=? AND expires_at<=?', (org_id, self.clock()))
            projects = db.execute('SELECT COUNT(*) FROM platform_projects WHERE org_id=?', (org_id,)).fetchone()[0]
            reserved = db.execute('SELECT COUNT(*) FROM project_reservations WHERE org_id=?', (org_id,)).fetchone()[0]
            if projects+reserved >= 1000:
                raise Denied('organization project quota exceeded')
            db.execute('INSERT INTO project_reservations VALUES(?,?,?)', (reservation, org_id, self.clock()+60))
        return reservation

    def release_project_reservation(self, reservation):
        with self.database.connection(write=True) as db:
            db.execute('DELETE FROM project_reservations WHERE reservation_id=?', (reservation,))

    def claim_project(self, principal, org_id, project_id, *, reservation=None):
        self.require_admin(principal, org_id)
        with self.database.connection(write=True) as db:
            suffix = ' FOR UPDATE' if self.database.postgres else ''
            db.execute('SELECT org_id FROM organizations WHERE org_id=?'+suffix, (org_id,)).fetchone()
            if db.execute('SELECT COUNT(*) FROM platform_projects WHERE org_id=?', (org_id,)).fetchone()[0] >= 1000:
                raise Denied('organization project quota exceeded')
            if reservation:
                slot = db.execute('SELECT 1 FROM project_reservations WHERE reservation_id=? AND org_id=? AND expires_at>?',
                                  (reservation, org_id, self.clock())).fetchone()
                if not slot:
                    raise Denied('project reservation expired')
                db.execute('DELETE FROM project_reservations WHERE reservation_id=?', (reservation,))
            db.execute('INSERT INTO platform_projects VALUES(?,?)', (project_id, org_id))
            db.execute('INSERT INTO project_members VALUES(?,?,?)', (project_id, principal.user_id, 'engineer'))

    def authorize(self, principal, project_id, *, write=False, review=False, details=False):
        with self.database.connection() as db:
            row = db.execute('SELECT pm.role,om.role AS org_role,p.org_id FROM platform_projects p '
                             'JOIN org_members om ON om.org_id=p.org_id AND om.user_id=? '
                             'LEFT JOIN project_members pm ON pm.project_id=p.project_id AND pm.user_id=om.user_id '
                             'WHERE p.project_id=?', (principal.user_id, project_id)).fetchone()
        allowed = row and (row['org_role'] == 'admin' or row['role'] in (
            ('reviewer',) if review else ('engineer',) if write else ('engineer', 'reviewer', 'viewer')))
        if not allowed:
            raise Denied('project access denied')
        if details:
            return {'org_id': row['org_id'], 'role': 'engineer' if row['org_role'] == 'admin' else row['role'],
                    'can_invite': row['org_role'] == 'admin',
                    'can_review': row['org_role'] == 'admin' or row['role'] == 'reviewer'}
        return row['org_id']

    def project_role(self, principal, project_id):
        self.authorize(principal, project_id)
        with self.database.connection() as db:
            row = db.execute('SELECT pm.role,om.role AS org_role FROM platform_projects p '
                             'JOIN org_members om ON om.org_id=p.org_id AND om.user_id=? '
                             'LEFT JOIN project_members pm ON pm.project_id=p.project_id AND pm.user_id=om.user_id '
                             'WHERE p.project_id=?', (principal.user_id, project_id)).fetchone()
        return 'engineer' if row['org_role'] == 'admin' else row['role']

    def invite(self, principal, project_id, email, role, *, lifetime_s=86400):
        org_id = self.authorize(principal, project_id)
        self.require_admin(principal, org_id)
        if role not in ('engineer', 'reviewer', 'viewer') or not 60 <= lifetime_s <= 604800:
            raise ValueError('invalid role or invitation lifetime')
        token = secrets.token_urlsafe(32)
        with self.database.connection(write=True) as db:
            db.execute('UPDATE invitations SET expires_at=? WHERE project_id=? AND email=? AND accepted_by IS NULL',
                       (self.clock(), project_id, email.strip().lower()))
            db.execute('INSERT INTO invitations VALUES(?,?,?,?,?,?,NULL)',
                       (token_hash(token), project_id, email.strip().lower(), role,
                        self.clock()+lifetime_s, principal.user_id))
        return {'invitation_token': token, 'invitation_id': token_hash(token), 'expires_in_s': lifetime_s}

    def revoke_invitation(self, principal, invitation_id):
        with self.database.connection() as db:
            row = db.execute('SELECT project_id FROM invitations WHERE token_hash=?', (invitation_id,)).fetchone()
        if row is None:
            raise Denied('invitation unavailable')
        org_id = self.authorize(principal, row['project_id'])
        self.require_admin(principal, org_id)
        with self.database.connection(write=True) as db:
            db.execute('UPDATE invitations SET expires_at=? WHERE token_hash=? AND accepted_by IS NULL',
                       (self.clock(), invitation_id))

    def accept(self, principal, token):
        with self.database.connection(write=True) as db:
            lock = ' FOR UPDATE' if self.database.postgres else ''
            row = db.execute('SELECT * FROM invitations WHERE token_hash=?'+lock, (token_hash(token),)).fetchone()
            if (row is None or row['accepted_by'] or row['expires_at'] <= self.clock()
                    or row['email'] != principal.email):
                raise Denied('invitation unavailable for this identity')
            org_id = db.execute('SELECT org_id FROM platform_projects WHERE project_id=?',
                                (row['project_id'],)).fetchone()[0]
            db.execute('INSERT OR IGNORE INTO org_members VALUES(?,?,?)', (org_id, principal.user_id, 'member'))
            db.execute('INSERT INTO project_members VALUES(?,?,?) ON CONFLICT(project_id,user_id) '
                       'DO UPDATE SET role=excluded.role', (row['project_id'], principal.user_id, row['role']))
            db.execute('UPDATE invitations SET accepted_by=? WHERE token_hash=?',
                       (principal.user_id, token_hash(token)))
        return {'project_id': row['project_id'], 'role': row['role']}

    def remove_member(self, principal, project_id, user_id):
        org_id = self.authorize(principal, project_id)
        self.require_admin(principal, org_id)
        with self.database.connection(write=True) as db:
            db.execute('DELETE FROM project_members WHERE project_id=? AND user_id=?', (project_id, user_id))
            db.execute('UPDATE invitations SET expires_at=? WHERE project_id=? AND email IN '
                       '(SELECT email FROM users WHERE user_id=?)', (self.clock(), project_id, user_id))

    def _artifact_lock(self, db):
        suffix = ' FOR UPDATE' if self.database.postgres else ''
        quota = db.execute('SELECT artifact_bytes FROM platform_quota WHERE quota_id=1'+suffix).fetchone()[0]
        db.execute('DELETE FROM artifact_reservations WHERE expires_at<=?', (self.clock(),))
        return quota

    def _artifact_budget(self, db, project_id, digest, size, quota):
        from physimesh.core.artifacts import ArtifactStore
        ArtifactStore._validate_digest(digest)
        if type(size) is not int or size < 0:
            raise ValueError('artifact size must be a nonnegative integer')
        if db.execute('SELECT 1 FROM platform_projects WHERE project_id=?', (project_id,)).fetchone() is None:
            raise Denied('project access denied')
        retained = db.execute('SELECT size_bytes FROM artifact_access WHERE project_id=? AND digest=?',
                              (project_id, digest)).fetchone()
        pending = db.execute('SELECT size_bytes FROM artifact_reservations WHERE project_id=? AND digest=? LIMIT 1',
                             (project_id, digest)).fetchone()
        if any(row is not None and row[0] != size for row in (retained, pending)):
            raise ValueError('artifact size differs from retained identity')
        if retained is not None or pending is not None:
            return retained is not None
        # Concurrent writes of the same project/digest consume one reservation;
        # another project's identical digest still consumes that project's budget.
        reserved = db.execute('SELECT COALESCE(SUM(size_bytes),0) AS global_bytes, '
            'COALESCE(SUM(CASE WHEN project_id=? THEN size_bytes ELSE 0 END),0) AS project_bytes, '
            'COALESCE(SUM(CASE WHEN project_id=? THEN 1 ELSE 0 END),0) AS project_count FROM '
            '(SELECT r.project_id,r.digest,MAX(r.size_bytes) AS size_bytes FROM artifact_reservations r '
            'WHERE NOT EXISTS (SELECT 1 FROM artifact_access a WHERE a.project_id=r.project_id AND a.digest=r.digest) '
            'GROUP BY r.project_id,r.digest) AS pending', (project_id, project_id)).fetchone()
        retained_stats = db.execute('SELECT COALESCE(SUM(size_bytes),0) AS bytes,COUNT(*) AS count '
                                   'FROM artifact_access WHERE project_id=?', (project_id,)).fetchone()
        if (retained_stats[0]+reserved[1]+size > 5_000_000_000 or quota+reserved[0]+size > 50_000_000_000
                or retained_stats[1]+reserved[2] >= 10000):
            raise Denied('project artifact budget exceeded')
        return False

    def reserve_artifact(self, project_id, digest, size):
        """Reserve admission for five minutes; pending writes confer no access."""
        with self.database.connection(write=True) as db:
            quota = self._artifact_lock(db)
            if self._artifact_budget(db, project_id, digest, size, quota):
                return None  # Existing entitlement belongs to a prior successful write.
            if db.execute('SELECT COUNT(*) FROM artifact_reservations WHERE project_id=?',
                          (project_id,)).fetchone()[0] >= 10000:
                raise Denied('project artifact reservation budget exceeded')
            reservation = ident('artifact')
            db.execute('INSERT INTO artifact_reservations VALUES(?,?,?,?,?)',
                       (reservation, project_id, digest, size, self.clock()+300))
            return reservation

    def finish_artifact(self, reservation):
        """Commit only a live write reservation, atomically granting and charging once."""
        if reservation is None:
            return
        with self.database.connection(write=True) as db:
            self._artifact_lock(db)
            row = db.execute('SELECT project_id,digest,size_bytes FROM artifact_reservations WHERE reservation_id=?',
                             (reservation,)).fetchone()
            if row is None:
                raise Denied('artifact write reservation expired or cancelled; retry publication')
            self._grant_artifact(db, row[0], row[1], row[2])
            db.execute('DELETE FROM artifact_reservations WHERE reservation_id=?', (reservation,))

    def cancel_artifact(self, reservation):
        if reservation is not None:
            with self.database.connection(write=True) as db:
                self._artifact_lock(db)
                db.execute('DELETE FROM artifact_reservations WHERE reservation_id=?', (reservation,))

    @staticmethod
    def _grant_artifact(db, project_id, digest, size):
        if db.execute('SELECT 1 FROM artifact_access WHERE project_id=? AND digest=?',
                      (project_id, digest)).fetchone() is None:
            db.execute('INSERT INTO artifact_access VALUES(?,?,?)', (project_id, digest, size))
            db.execute('UPDATE platform_quota SET artifact_bytes=artifact_bytes+? WHERE quota_id=1', (size,))

    def grant_artifact(self, project_id, digest, size):
        """Associate already-persisted bytes, respecting concurrent pending admissions."""
        with self.database.connection(write=True) as db:
            quota = self._artifact_lock(db)
            self._artifact_budget(db, project_id, digest, size, quota)
            self._grant_artifact(db, project_id, digest, size)

    def require_artifact(self, project_id, digest):
        with self.database.connection() as db:
            row = db.execute('SELECT 1 FROM artifact_access WHERE project_id=? AND digest=?',
                             (project_id, digest)).fetchone()
        if row is None:
            raise Denied('artifact access denied')

    def review(self, principal, project_id, study, result, decision, comment):
        self.authorize(principal, project_id)
        if decision == 'comment':
            if self.project_role(principal, project_id) not in ('engineer', 'reviewer'):
                raise Denied('engineer or reviewer role required to comment')
        else:
            self.authorize(principal, project_id, review=True)
        if decision not in ('comment', 'accepted', 'changes_requested') or len(comment) > 10000:
            raise ValueError('invalid review')
        record = {'review_id': ident('review'), 'project_id': project_id, 'study_sha256': study,
                  'result_sha256': result, 'user_id': principal.user_id, 'decision': decision,
                  'comment': comment, 'created_at': self.clock()}
        with self.database.connection(write=True) as db:
            suffix = ' FOR UPDATE' if self.database.postgres else ''
            db.execute('SELECT project_id FROM platform_projects WHERE project_id=?'+suffix, (project_id,)).fetchone()
            if db.execute('SELECT COUNT(*) FROM reviews WHERE project_id=?', (project_id,)).fetchone()[0] >= 10000:
                raise Overloaded('project review history budget exceeded')
            db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)', tuple(record.values()))
        return {**record, 'qualification': 'Authenticated workflow review; not aircraft/model qualification.'}


class OIDCVerifier:
    def __init__(self, issuer, audience, jwks_url):
        from urllib.parse import urlparse

        import jwt
        if any(urlparse(url).scheme != 'https' for url in (issuer, jwks_url)):
            raise ValueError('OIDC issuer and JWKS require HTTPS')
        self.issuer, self.audience = issuer, audience
        self.keys = jwt.PyJWKClient(jwks_url, timeout=5, cache_keys=False, lifespan=300)

    def verify(self, token):
        import jwt
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=['RS256', 'ES256'], audience=self.audience,
                              issuer=self.issuer, options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']})
        except jwt.PyJWTError as exc:
            raise InvalidSession('invalid OIDC access token') from exc
