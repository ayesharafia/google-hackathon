"""Bounded metadata connections for explicit local SQLite or hosted PostgreSQL."""
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Overloaded(Exception):
    """A bounded metadata queue/lock could not be acquired; retry with backoff."""


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PGConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, args=()):
        sql = sql.replace('?', '%s')
        if 'INSERT OR IGNORE INTO' in sql:
            sql = sql.replace('INSERT OR IGNORE INTO', 'INSERT INTO') + ' ON CONFLICT DO NOTHING'
        return self.connection.execute(sql, args)


class MetadataDB:
    def __init__(self, path: Path | None = None, *, url=None, pool_size=8, schema=None):
        if (path is None) == (url is None):
            raise ValueError('select exactly one metadata database')
        self.path = Path(path) if path is not None else None
        self.postgres = url is not None
        self.pool = None
        if schema is not None and re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema) is None:
            raise ValueError('invalid trusted metadata schema')
        if url:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            self.pool = ConnectionPool(url, open=True, min_size=1, max_size=pool_size, timeout=2,
                                       max_waiting=pool_size*8, kwargs={'row_factory': dict_row, **({'options': '-csearch_path='+schema} if schema else {})})
            self.pool.wait(timeout=20)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self, *, write=False):
        if self.postgres:
            from psycopg import InterfaceError, OperationalError
            from psycopg.errors import LockNotAvailable, QueryCanceled
            from psycopg_pool import PoolTimeout, TooManyRequests
            try:
                with self.pool.connection() as connection, connection.transaction():
                    connection.execute("SET LOCAL lock_timeout = '2s'")
                    connection.execute("SET LOCAL statement_timeout = '15s'")
                    original = connection.row_factory
                    from psycopg.rows import dict_row
                    def rows(cursor):
                        factory = dict_row(cursor)
                        return lambda values: Row(factory(values))
                    connection.row_factory = rows
                    try:
                        yield PGConnection(connection)
                    finally:
                        connection.row_factory = original
            except (PoolTimeout, TooManyRequests, LockNotAvailable, QueryCanceled, OperationalError, InterfaceError) as exc:
                raise Overloaded('metadata capacity exceeded; retry later') from exc
        else:
            connection = sqlite3.connect(self.path, timeout=2, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            try:
                connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                yield connection
                connection.commit()
            except sqlite3.OperationalError as exc:
                connection.rollback()
                if 'locked' in str(exc) or 'busy' in str(exc):
                    raise Overloaded('local metadata is busy; retry later') from exc
                raise
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

    def close(self):
        if self.pool:
            self.pool.close()
