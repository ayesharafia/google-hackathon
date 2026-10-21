"""Local SQLite/file snapshot and verified restore; hosted RPO/RTO are separate gates."""
import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _integrity(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as database:
        if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('database integrity check failed')


def backup_local(data_root: Path, destination: Path):
    """Quiesce API/workers first; files are immutable and SQLite backup transactional.

    Retain the returned manifest digest separately. Covers platform metadata and
    artifacts, not legacy CFD directories or remote S3.
    """
    if destination.exists():
        raise ValueError('backup destination must be new')
    if destination.resolve().is_relative_to(data_root.resolve()):
        raise ValueError('backup must be outside its live data root')
    if any(path.is_symlink() for path in (data_root/'projects.sqlite', data_root/'artifacts')):
        raise ValueError('snapshot source cannot contain symlinks')
    if not (data_root/'projects.sqlite').is_file() or not (data_root/'artifacts').is_dir():
        raise ValueError('platform database and artifact directory must exist')
    if any(path.is_symlink() for path in (data_root/'artifacts').rglob('*')):
        raise ValueError('snapshot source cannot contain symlinks')
    started = time.perf_counter()
    destination.mkdir(parents=True, mode=0o700)
    source = sqlite3.connect((data_root/'projects.sqlite').resolve().as_uri()+'?mode=ro', uri=True)
    target = sqlite3.connect(destination/'projects.sqlite')
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    _integrity(destination/'projects.sqlite')
    shutil.copytree(data_root/'artifacts', destination/'artifacts')
    objects = 0
    with (destination/'manifest.jsonl').open('w') as manifest:
        for path in sorted(destination.rglob('*')):
            if path.is_symlink():
                raise ValueError('snapshot cannot contain symlinks')
            if path.is_file() and path.name != 'manifest.jsonl':
                manifest.write(json.dumps({'path': str(path.relative_to(destination)), 'sha256': _digest(path),
                                           'bytes': path.stat().st_size})+'\n')
                objects += 1
    return {'files': objects, 'manifest_sha256': _digest(destination/'manifest.jsonl'),
            'wall_s': time.perf_counter()-started,
            'qualification': 'Local SQLite/file snapshot; not a hosted RPO/RTO demonstration.'}


def restore_local(backup: Path, destination: Path, *, manifest_sha256: str):
    if destination.exists():
        raise ValueError('restore destination must be new; never overwrite live data')
    manifest = backup/'manifest.jsonl'
    if manifest.is_symlink() or any(path.is_symlink() for path in backup.rglob('*')):
        raise ValueError('snapshot cannot contain symlinks')
    if _digest(manifest) != manifest_sha256:
        raise ValueError('backup manifest integrity failed')
    started, verified = time.perf_counter(), {}
    for line in manifest.read_text().splitlines():
        entry = json.loads(line)
        name = Path(entry['path'])
        path = backup/name
        if name.is_absolute() or '..' in name.parts or not name.parts or name in verified:
            raise ValueError('invalid backup manifest path')
        if path.is_symlink() or not path.resolve().is_relative_to(backup.resolve()):
            raise ValueError('backup manifest path escapes its root')
        if path.stat().st_size != entry['bytes'] or _digest(path) != entry['sha256']:
            raise ValueError('backup file integrity failed')
        verified[name] = entry
    actual = {path.relative_to(backup) for path in backup.rglob('*') if path.is_file() and path != manifest}
    if actual != set(verified) or Path('projects.sqlite') not in verified:
        raise ValueError('backup contains missing or unlisted files')
    destination.mkdir(parents=True, mode=0o700)
    for name, entry in verified.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup/name, target)
        if target.stat().st_size != entry['bytes'] or _digest(target) != entry['sha256']:
            raise ValueError('restored file integrity failed')
    _integrity(destination/'projects.sqlite')
    return {'wall_s': time.perf_counter()-started, 'files': len(verified),
            'qualification': 'Restore to a fresh local root; no external target.'}
