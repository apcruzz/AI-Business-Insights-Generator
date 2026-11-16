"""Persistent account/session storage. Uploaded business data never enters this database."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

PASSWORD_METHOD = 'pbkdf2:sha256:600000'
SESSION_SECONDS = 3600
USERNAME = re.compile(r'[a-z0-9][a-z0-9_.-]{2,31}\Z')


class AccountConflict(ValueError):
    pass


class AccountUnavailable(RuntimeError):
    pass


def username(value):
    # Store one canonical spelling so casing and surrounding spaces cannot create duplicate logins.
    if not isinstance(value, str) or not USERNAME.fullmatch(value.strip().lower()):
        raise ValueError('Use a username of 3–32 letters, numbers, dots, underscores or hyphens, starting with a letter or number.')
    return value.strip().lower()


def display_name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80 or any(ord(c) < 32 for c in value):
        raise ValueError('Enter a display name of 1–80 characters.')
    return value.strip()


def password(value):
    if not isinstance(value, str) or not 16 <= len(value) <= 256:
        raise ValueError('Use a password between 16 and 256 characters.')
    return value


def public_user(row):
    # Explicitly select browser-visible fields; never serialize password hashes or session secrets.
    return {'id': row['id'], 'username': row['username'], 'displayName': row['display_name'],
            'createdAt': datetime.fromtimestamp(row['created_at'], timezone.utc).isoformat()}


def token_hash(value):
    # The cookie contains a random bearer token; a database leak should reveal only its digest.
    return hashlib.sha256(value.encode()).hexdigest()


class AccountStore:
    def __init__(self, database_url, origin):
        self.sqlite_path = None
        self.database_url = database_url
        if database_url.startswith('sqlite:///'):
            # SQLite is solely a loopback development/test fixture, never hosted storage.
            path = database_url[len('sqlite:///'):]
            if urlsplit(origin).hostname not in ('127.0.0.1', 'localhost', '::1') or not Path(path).is_absolute():
                raise RuntimeError('Hosted accounts require persistent PostgreSQL, not a local SQLite file.')
            self.sqlite_path = path
        elif urlsplit(database_url).scheme not in ('postgres', 'postgresql') or not urlsplit(database_url).hostname:
            raise RuntimeError('Set DATABASE_URL to a persistent PostgreSQL connection string for AUTH_MODE=accounts.')
        self.initialize()
        # Missing-user sign-in still performs the same password-hash work.
        self.dummy_hash = generate_password_hash(secrets.token_urlsafe(32), method=PASSWORD_METHOD)

    @contextmanager
    def transaction(self):
        # Use a fresh connection per operation and always commit, roll back, and close it here.
        connection = None
        try:
            if self.sqlite_path:
                connection = sqlite3.connect(self.sqlite_path, timeout=5)
                connection.row_factory = sqlite3.Row
                connection.execute('PRAGMA foreign_keys=ON')
            else:
                import psycopg
                from psycopg.rows import dict_row
                host = urlsplit(self.database_url).hostname
                local = host in ('localhost', '127.0.0.1', '::1')
                internal = host.endswith('.internal')
                # External database connections always verify both the certificate and hostname.
                tls = {} if local or internal else {'sslmode': 'verify-full', 'sslrootcert': 'system'}
                connection = psycopg.connect(self.database_url, connect_timeout=10,
                    row_factory=dict_row, prepare_threshold=None, **tls)
                connection.execute("SET LOCAL statement_timeout = '10000'")
            yield connection
            connection.commit()
        except Exception as exc:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
            if isinstance(exc, (ValueError, AccountConflict)):
                raise
            if isinstance(exc, sqlite3.IntegrityError) or getattr(exc, 'sqlstate', None) == '23505':
                raise AccountConflict('That username is unavailable. Choose another.') from None
            raise AccountUnavailable('Account storage is temporarily unavailable. Try again shortly.') from None
        finally:
            if connection:
                connection.close()

    def execute(self, connection, sql, params=()):
        # SQL is fixed application text; every value remains a bound parameter.
        return connection.execute(sql if self.sqlite_path else sql.replace('?', '%s'), params)

    def initialize(self):
        # These tables hold identities and revocable sessions, not uploaded sales records.
        try:
            with self.transaction() as connection:
                self.execute(connection, '''CREATE TABLE IF NOT EXISTS dashboard_users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
                    created_at BIGINT NOT NULL)''')
                self.execute(connection, '''CREATE TABLE IF NOT EXISTS dashboard_sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES dashboard_users(id) ON DELETE CASCADE,
                    csrf TEXT NOT NULL, created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL)''')
                self.execute(connection, 'CREATE INDEX IF NOT EXISTS dashboard_sessions_user ON dashboard_sessions(user_id)')
                self.execute(connection, 'CREATE INDEX IF NOT EXISTS dashboard_sessions_expiry ON dashboard_sessions(expires_at)')
        except AccountUnavailable:
            raise RuntimeError('Cannot initialize account storage. Check DATABASE_URL and database connectivity.') from None

    def register(self, payload):
        # An immutable ID keeps dataset ownership stable even when the username changes later.
        name = username(payload.get('username'))
        supplied_name = payload.get('displayName')
        label = display_name(name if supplied_name is None or supplied_name == '' else supplied_name)
        hashed = generate_password_hash(password(payload.get('password')), method=PASSWORD_METHOD)
        row = {'id': str(uuid.uuid4()), 'username': name, 'display_name': label,
               'password_hash': hashed, 'created_at': int(time.time())}
        with self.transaction() as connection:
            self.execute(connection, 'INSERT INTO dashboard_users (id, username, display_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)',
                         tuple(row[key] for key in ('id', 'username', 'display_name', 'password_hash', 'created_at')))
        return row

    def authenticate(self, name, supplied_password):
        # Normalize invalid inputs without revealing whether an account exists.
        name = name.strip().lower() if isinstance(name, str) and len(name) <= 80 else ''
        supplied_password = supplied_password if isinstance(supplied_password, str) and len(supplied_password) <= 256 else ''
        with self.transaction() as connection:
            row = self.execute(connection, 'SELECT * FROM dashboard_users WHERE username = ?', (name,)).fetchone()
            row = dict(row) if row else None
        valid = check_password_hash(row['password_hash'] if row else self.dummy_hash, supplied_password)
        return row if row and valid else None

    def create_session(self, user, old_token=None):
        # Rotate both browser credentials after sign-in; neither token is derived from a username.
        raw, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), int(time.time())
        with self.transaction() as connection:
            # A concurrent password change/deletion cannot issue a session for stale credentials.
            suffix = '' if self.sqlite_path else ' FOR UPDATE'
            current = self.execute(connection, 'SELECT password_hash FROM dashboard_users WHERE id = ?' + suffix, (user['id'],)).fetchone()
            if not current or current['password_hash'] != user['password_hash']:
                raise ValueError('Account credentials changed. Sign in again.')
            self.execute(connection, 'DELETE FROM dashboard_sessions WHERE expires_at <= ?', (now,))
            if old_token:
                self.execute(connection, 'DELETE FROM dashboard_sessions WHERE token_hash = ?', (token_hash(old_token),))
            sessions = self.execute(connection, 'SELECT token_hash FROM dashboard_sessions WHERE user_id = ? ORDER BY created_at DESC, token_hash', (user['id'],)).fetchall()
            # Keep nine existing sessions before inserting the new one: ten active sessions at most.
            for entry in sessions[9:]:
                self.execute(connection, 'DELETE FROM dashboard_sessions WHERE token_hash = ?', (entry['token_hash'],))
            self.execute(connection, 'INSERT INTO dashboard_sessions (token_hash, user_id, csrf, created_at, expires_at) VALUES (?, ?, ?, ?, ?)',
                         (token_hash(raw), user['id'], csrf, now, now + SESSION_SECONDS))
        return raw, csrf

    def session(self, raw):
        # Reject malformed cookies before querying storage, then require a session that has not expired.
        if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', raw):
            return None
        with self.transaction() as connection:
            row = self.execute(connection, '''SELECT u.*, s.csrf, s.token_hash FROM dashboard_sessions s
                JOIN dashboard_users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?''',
                (token_hash(raw), int(time.time()))).fetchone()
            return dict(row) if row else None

    def logout(self, raw):
        with self.transaction() as connection:
            self.execute(connection, 'DELETE FROM dashboard_sessions WHERE token_hash = ?', (token_hash(raw),))

    def update(self, user, payload):
        # Profile edits need the current password too; possessing a session alone is insufficient.
        if not check_password_hash(user['password_hash'], payload.get('currentPassword') if isinstance(payload.get('currentPassword'), str) and len(payload['currentPassword']) <= 256 else ''):
            raise ValueError('Current password is incorrect.')
        name = username(payload.get('username', user['username']))
        label = display_name(payload.get('displayName', user['display_name']))
        hashed = generate_password_hash(password(payload['newPassword']), method=PASSWORD_METHOD) if 'newPassword' in payload else user['password_hash']
        with self.transaction() as connection:
            result = self.execute(connection, 'UPDATE dashboard_users SET username = ?, display_name = ?, password_hash = ? WHERE id = ? AND password_hash = ?',
                                  (name, label, hashed, user['id'], user['password_hash']))
            if not result.rowcount:
                raise ValueError('Account credentials changed. Sign in again.')
            # Reauthenticate all devices after any account change.
            self.execute(connection, 'DELETE FROM dashboard_sessions WHERE user_id = ?', (user['id'],))
        return {**user, 'username': name, 'display_name': label, 'password_hash': hashed}

    def delete(self, user, supplied_password):
        # The password predicate detects concurrent credential changes; the foreign key removes sessions.
        if not isinstance(supplied_password, str) or len(supplied_password) > 256 or not check_password_hash(user['password_hash'], supplied_password):
            raise ValueError('Current password is incorrect.')
        with self.transaction() as connection:
            result = self.execute(connection, 'DELETE FROM dashboard_users WHERE id = ? AND password_hash = ?', (user['id'], user['password_hash']))
            if not result.rowcount:
                raise ValueError('Account credentials changed. Sign in again.')
