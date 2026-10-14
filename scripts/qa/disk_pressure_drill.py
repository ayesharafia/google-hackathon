#!/usr/bin/env python3
"""Bounded, injected ENOSPC drill using local ArtifactStore and SQLite jobs."""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from physimesh.core.artifacts import ArtifactStore
from physimesh.platform.database import MetadataDB
from physimesh.platform.jobs import Jobs, StaleAttempt

PAYLOAD = b'PhysiCore synthetic disk-pressure fixture\n' * 8
PROJECT = 'synthetic_disk_pressure'


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _deny_stale(jobs: Jobs, claim: dict) -> None:
    try:
        jobs.complete(claim, {'artifact_sha256': '0' * 64})
    except StaleAttempt:
        return
    raise RuntimeError('stale publication was accepted')


def _scenario(root: Path, stage: str) -> dict:
    database = MetadataDB(root / 'jobs.sqlite')
    try:
        return _exercise(root, stage, database)
    finally:
        database.close()


def _exercise(root: Path, stage: str, database: MetadataDB) -> dict:
    """Inject at first-write link, after a real small tempfile write/fsync."""
    now = [1000.0]
    jobs = Jobs(database, clock=lambda: now[0], lease_s=5)
    # Minimal synthetic foreign-key fixture; no accounts or credentials needed.
    with database.connection(write=True) as db:
        db.execute('INSERT INTO organizations VALUES(?,?,?)', ('synthetic_org', 'Disposable drill', now[0]))
        db.execute('INSERT INTO platform_projects VALUES(?,?)', (PROJECT, 'synthetic_org'))
    store = ArtifactStore(root / 'artifacts')
    sha = hashlib.sha256(PAYLOAD).hexdigest()
    submitted = jobs.submit(PROJECT, 'study', {'fixture': 'disk-pressure', 'stage': stage}, max_attempts=3)
    failed = jobs.claim('synthetic-first-worker')
    _require(failed is not None, 'initial claim unavailable')
    original_link = os.link
    injected = []

    def link_with_enospc(source, target, *args, **kwargs):
        target = Path(target)
        intended = store._obj(sha) if stage == 'object' else store.root / 'meta' / f'{sha}.json'
        if target == intended:
            injected.append(stage)
            raise OSError(errno.ENOSPC, 'synthetic injected ENOSPC')
        return original_link(source, target, *args, **kwargs)

    try:
        with patch('physimesh.core.artifacts.os.link', side_effect=link_with_enospc):
            store.put_bytes(PAYLOAD, kind='synthetic-fixture', meta={'source': 'disposable drill'})
    except OSError as exc:
        _require(exc.errno == errno.ENOSPC and injected == [stage], 'unexpected storage failure')
        # Exercise the real retry path without retaining paths or exception text.
        jobs.fail(failed, 'synthetic injected ENOSPC', retry=True)
    else:
        raise RuntimeError('injected failure did not occur')
    retained = jobs.get(PROJECT, submitted['job_id'])
    _require(retained['state'] == 'queued' and retained['result_json'] is None,
             'failure left an accepted job result')
    _require(not (store.root / 'meta' / f'{sha}.json').exists(), 'metadata unexpectedly published')
    object_present = store._obj(sha).exists()
    _require(object_present == (stage == 'metadata'), 'unexpected partial artifact state')
    # Enumerate actual store files: no unnamed temporary files may survive.
    files = [p for p in store.root.rglob('*') if p.is_file()]
    _require(files == ([store._obj(sha)] if object_present else []), 'store tempfile survived ENOSPC')
    _deny_stale(jobs, failed)
    # Retry backoff and lease expiry are accelerated through an injected clock.
    _require(jobs.claim('too-early-worker') is None, 'retry backoff bypassed')
    now[0] += 2
    interrupted = jobs.claim('synthetic-retry-worker')
    _require(interrupted is not None and interrupted['generation'] == 2, 'retry claim unavailable')
    now[0] += 6
    _deny_stale(jobs, interrupted)
    recovered = jobs.claim('synthetic-recovery-worker')
    _require(recovered is not None and recovered['generation'] == 3, 'expired lease did not recover')
    digest = store.put_bytes(PAYLOAD, kind='synthetic-fixture', meta={'source': 'disposable drill'})
    with store.open(digest) as artifact:
        _require(artifact.read() == PAYLOAD, 'recovered artifact bytes differ')
    _require(store.meta(digest)['size'] == len(PAYLOAD), 'recovered metadata differs')
    jobs.complete(recovered, {'artifact_sha256': digest, 'fixture': 'synthetic'})
    accepted = jobs.get(PROJECT, submitted['job_id'])
    original_result = accepted['result_json']
    _deny_stale(jobs, failed)
    _deny_stale(jobs, interrupted)
    _deny_stale(jobs, recovered)
    _require(jobs.get(PROJECT, submitted['job_id'])['result_json'] == original_result,
             'stale publication mutated accepted result')
    reopened = MetadataDB(root / 'jobs.sqlite')
    try:
        persisted = Jobs(reopened, clock=lambda: now[0]).get(PROJECT, submitted['job_id'])
        _require(persisted['state'] == 'succeeded' and persisted['result_json'] == original_result,
                 'accepted result did not persist')
        attempt_states = [a['state'] for a in persisted['attempts']]
        _require(attempt_states == ['failed', 'expired', 'accepted'], 'unexpected attempt history')
    finally:
        reopened.close()
    return {
        'injection_stage': stage + '_first_write_link', 'errno': 'ENOSPC',
        'temporary_file_cleanup': 'passed', 'job_result_after_failure': None,
        'partial_object_after_failure': object_present,
        'partial_metadata_after_failure': False, 'retry_backoff': 'passed',
        'lease_expiry_recovery': 'passed', 'stale_publication_rejected': 'passed',
        'accepted_result_immutable': 'passed', 'sqlite_reopen': 'passed',
        'recovered_artifact_integrity': 'passed', 'attempt_states': attempt_states,
        'payload_bytes': len(PAYLOAD),
    }


def run_drill() -> dict:
    """Two fixed scenarios; own all temporary files and clean on success/error."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='physicore-disk-drill-') as directory:
        root = Path(directory)
        scenarios = []
        for stage in ('object', 'metadata'):
            stage_root = root / stage
            stage_root.mkdir()
            scenarios.append(_scenario(stage_root, stage))
        observed_bytes = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        _require(observed_bytes <= 4 * 1024 * 1024, 'observed disposable file budget exceeded')
    _require(not root.exists(), 'disposable directory survived cleanup')
    return {
        'elapsed_s': round(time.monotonic() - started, 6),
        'observed_disposable_file_bytes_at_end': observed_bytes,
        'schema_version': 1, 'fixture': 'synthetic local storage and job bookkeeping',
        'failure_mode': 'injected ENOSPC; no actual filesystem exhaustion',
        'injection_boundary': 'ArtifactStore os.link after bounded temporary write/fsync',
        'lease_time': 'injected clock: 2-second retry backoff and 6-second lease advance',
        'atomicity_scope': 'ArtifactStore object and metadata writes are separate; job completion is separate',
        'not_verified': ['actual disk/quota exhaustion', 'write/flush/fsync ENOSPC',
                         'SQLite ENOSPC', 'PostgreSQL', 'hosted object storage',
                         'worker/solver integration', 'cross-store atomic transaction'],
        'limits': {'scenarios': 2, 'attempts_per_scenario': 3, 'artifact_payload_bytes': len(PAYLOAD),
                   'observed_file_bytes_ceiling': 4 * 1024 * 1024},
        'scenarios': scenarios, 'disposable_directory_cleanup': 'passed',
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True, help='sanitized JSON output path')
    args = parser.parse_args(argv)
    if args.receipt.exists():
        parser.error('receipt already exists; choose a new output path')
    receipt = run_drill()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x', encoding='utf-8') as output:
        output.write(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(receipt, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
