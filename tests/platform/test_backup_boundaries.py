"""Recovery must retain WAL commits and refuse links outside the snapshot."""
import hashlib
import sqlite3

import pytest

from physimesh.platform.backup import backup_local, restore_local


def live_root(tmp_path):
    root = tmp_path/'live'
    root.mkdir()
    with sqlite3.connect(root/'projects.sqlite') as db:
        db.execute('CREATE TABLE evidence(value TEXT)')
    (root/'artifacts').mkdir()
    (root/'artifacts/object').write_bytes(b'original evidence')
    return root


@pytest.mark.parametrize('member', ['projects.sqlite', 'artifacts'])
def test_backup_refuses_linked_source_roots_before_creating_destination(tmp_path, member):
    root = live_root(tmp_path)
    source = root/member
    external = tmp_path/member
    source.rename(external)
    source.symlink_to(external, target_is_directory=external.is_dir())
    destination = tmp_path/'snapshot'
    with pytest.raises(ValueError, match='symlinks'):
        backup_local(root, destination)
    assert not destination.exists()
    if external.is_dir():
        assert (external/'object').read_bytes() == b'original evidence'
    else:
        assert external.is_file()


@pytest.mark.parametrize('link_kind', ['manifest', 'empty_directory', 'dangling'])
def test_restore_refuses_all_links_before_creating_destination(tmp_path, link_kind):
    snapshot = tmp_path/'snapshot'
    receipt = backup_local(live_root(tmp_path), snapshot)
    if link_kind == 'manifest':
        external = tmp_path/'external-manifest'
        (snapshot/'manifest.jsonl').rename(external)
        (snapshot/'manifest.jsonl').symlink_to(external)
    elif link_kind == 'empty_directory':
        external = tmp_path/'private-empty'
        external.mkdir()
        (snapshot/'unlisted').symlink_to(external, target_is_directory=True)
    else:
        (snapshot/'unlisted').symlink_to(tmp_path/'missing')
    destination = tmp_path/'restored'
    with pytest.raises(ValueError, match='symlinks'):
        restore_local(snapshot, destination, manifest_sha256=receipt['manifest_sha256'])
    assert not destination.exists()


def test_backup_retains_committed_wal_without_checkpoint_or_changing_source(tmp_path):
    root = live_root(tmp_path)
    database = root/'projects.sqlite'
    with sqlite3.connect(database) as source:
        assert source.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        source.execute('PRAGMA wal_autocheckpoint=0')
        source.execute("INSERT INTO evidence VALUES ('accepted WAL commit')")
        source.commit()
        wal = root/'projects.sqlite-wal'
        assert wal.stat().st_size > 0
        original_wal = hashlib.sha256(wal.read_bytes()).hexdigest()
        receipt = backup_local(root, tmp_path/'snapshot')
        restore_local(tmp_path/'snapshot', tmp_path/'restored', manifest_sha256=receipt['manifest_sha256'])
        assert hashlib.sha256(wal.read_bytes()).hexdigest() == original_wal
        with sqlite3.connect(tmp_path/'restored/projects.sqlite') as restored:
            assert restored.execute('SELECT value FROM evidence').fetchall() == [('accepted WAL commit',)]
