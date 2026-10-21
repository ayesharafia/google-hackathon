#!/usr/bin/env python3
"""Start bounded disposable PostgreSQL test service; keep credentials in private ignored state."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

POSTGRES = 'postgres@sha256:c6222b54873a2fb19591cb06b93ef2825c03cdb680396e3600f24921f340f630'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'test', 'stop'))
    parser.add_argument('--state', type=Path, default=Path('.backend/platform-services'))
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = args.state/'private.json'
    if args.action == 'stop':
        if not state.exists():
            print('No disposable PostgreSQL service state; nothing to stop.')
            return
        record = json.loads(state.read_text())
        subprocess.run(['docker', 'rm', '-f', record['container']], check=True, capture_output=True)
        state.unlink()
        print('Disposable PostgreSQL service stopped.')
        return
    if args.action == 'test':
        record = json.loads(state.read_text())
        subprocess.run([str(Path('.venv/bin/python')), '-m', 'pytest', '-q',
                        'tests/platform/test_postgres_integration.py'], check=True,
                       env={**os.environ, 'PHYSIMESH_TEST_DATABASE_URL': record['url']})
        return
    if state.exists():
        raise ValueError('service state already exists; use test or stop')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    password = secrets.token_urlsafe(32)
    environment = args.state/'postgres.env'
    environment.touch(mode=0o600)
    environment.write_text('POSTGRES_USER=physimesh\nPOSTGRES_DB=physimesh\nPOSTGRES_PASSWORD='+password+'\n')
    name = 'physimesh-pg-'+secrets.token_hex(6)
    try:
        result = subprocess.run(['docker', 'run', '--detach', '--name', name, '--env-file', str(environment),
            '--publish', f'127.0.0.1:{port}:5432', '--cpus', '1', '--memory', '1g', '--pids-limit', '128',
            '--user', '999:999', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only',
            '--tmpfs', '/var/lib/postgresql/data:rw,uid=999,gid=999,size=512m',
            '--tmpfs', '/tmp:rw,size=64m', '--tmpfs', '/var/run/postgresql:rw,uid=999,gid=999,size=16m', POSTGRES],
            capture_output=True, text=True, check=True)
    finally:
        environment.unlink(missing_ok=True)
    url = f'postgresql://physimesh:{password}@127.0.0.1:{port}/physimesh'
    state.touch(mode=0o600)
    state.write_text(json.dumps({'container': name, 'url': url, 'image': POSTGRES}))
    import psycopg
    for _ in range(60):
        try:
            with psycopg.connect(url, connect_timeout=1) as connection:
                connection.execute('SELECT 1')
            print(json.dumps({'service': 'PostgreSQL', 'ready': True, 'image': POSTGRES,
                              'container': result.stdout.strip()}))
            return
        except psycopg.OperationalError:
            time.sleep(.5)
    raise RuntimeError('PostgreSQL readiness timed out; private state retained for cleanup')


if __name__ == '__main__':
    main()
