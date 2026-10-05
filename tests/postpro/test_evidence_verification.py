"""Independent byte scopes, not numerical reproduction or aircraft approval."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from physimesh.postpro.baseline import fingerprint, verify_baseline
from physimesh.postpro.evidence_verification import verify_evidence, verify_source_commit

pytest_plugins = ('tests.postpro.test_baseline',)


def test_later_source_changes_do_not_requalify_or_break_evidence_scope(frozen):
    repo, _, _, inventory = frozen
    (repo/'src/calculation.py').write_text('raise RuntimeError("never execute me")\n')
    result = verify_evidence(repo, inventory, native=True, vendor=True)
    assert not result['current_source_checked'] and not result['solver_rerun']
    assert result['native_outputs_checked'] == 3 and result['documentary_records_checked'] == 1
    assert result['evidence'] == 'unverified' and result['machine_review'] == 'pending'
    assert result['aircraft_validation'] == 'not_established'
    assert result['recorded_claude_review']['verification'] == 'document bytes only'
    with pytest.raises(ValueError, match='src/calculation.py'):
        verify_baseline(repo, inventory)


@pytest.mark.parametrize('name', ['docs/review.md', 'data/examples/screening.json',
                                 'native/coarse/system/controlDict', 'native/coarse/fields/value',
                                 'native/coarse/run_record.json', 'vendor/archive.tgz'])
def test_evidence_document_support_native_and_vendor_tampering_refuses(frozen, name):
    repo, _, _, inventory = frozen
    (repo/name).write_bytes(b'tampered')
    with pytest.raises(ValueError):
        verify_evidence(repo, inventory, native=True, vendor=True)


@pytest.mark.parametrize('name', ['results.json', 'run_group.json', 'plots/pressure.png', 'hashes.json'])
def test_package_tampering_refuses(frozen, name):
    repo, _, package, inventory = frozen
    (package/name).write_bytes(b'tampered')
    with pytest.raises(ValueError):
        verify_evidence(repo, inventory)


def test_unrequested_native_and_vendor_scopes_are_reported_unchecked(frozen):
    repo, _, _, inventory = frozen
    (repo/'vendor/archive.tgz').unlink()
    (repo/'native/coarse/fields/value').unlink()
    result = verify_evidence(repo, inventory)
    assert not result['native_checked'] and not result['vendor_checked']
    assert result['native_outputs_checked'] == 0


def test_package_membership_escape_and_relocation(frozen, tmp_path):
    repo, data, package, inventory = frozen
    relocated = tmp_path/'relocated'; shutil.copytree(data, relocated)
    assert verify_evidence(repo, inventory, data_root=relocated)['package_id'] == inventory.package.group_id
    (package/'unexpected.txt').write_text('extra')
    with pytest.raises(ValueError, match='unexpected'):
        verify_evidence(repo, inventory)
    (package/'unexpected.txt').unlink()
    original = (package/'plots/pressure.png').read_bytes()
    outside = tmp_path/'outside.png'; outside.write_bytes(original)
    (package/'plots/pressure.png').unlink(); (package/'plots/pressure.png').symlink_to(outside)
    with pytest.raises(ValueError, match='escapes'):
        verify_evidence(repo, inventory)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def committed_source(frozen):
    repo, _, _, inventory = frozen
    git(repo, 'init', '-q')
    git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'add', 'src/calculation.py')
    git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Fixture source')
    commit = git(repo, 'rev-parse', 'HEAD')
    return repo, inventory.model_copy(update={'source': inventory.source.model_copy(update={'commit': commit})})


def test_exact_git_source_bytes_read_without_checkout_or_execution(frozen):
    repo, inventory = committed_source(frozen)
    (repo/'src/calculation.py').write_text('raise RuntimeError("never execute me")\n')
    head = git(repo, 'rev-parse', 'HEAD')
    status = git(repo, 'status', '--porcelain')
    report = verify_source_commit(repo, inventory)
    assert report['source_commit'] == head and report['source_files_checked'] == 1
    assert not report['current_source_checked'] and not report['solver_rerun']
    assert git(repo, 'rev-parse', 'HEAD') == head and git(repo, 'status', '--porcelain') == status


def test_missing_commit_wrong_digest_missing_path_and_symlink_refuse(frozen):
    repo, inventory = committed_source(frozen)
    missing = inventory.model_copy(update={'source': inventory.source.model_copy(update={'commit': 'f'*40})})
    with pytest.raises(ValueError, match='unavailable'):
        verify_source_commit(repo, missing)
    bad = fingerprint(repo/'src/calculation.py').model_copy(update={'sha256': 'f'*64})
    wrong = inventory.model_copy(update={'source': inventory.source.model_copy(update={'files': {'src/calculation.py': bad}})})
    with pytest.raises(ValueError, match='bytes differ'):
        verify_source_commit(repo, wrong)
    absent = inventory.model_copy(update={'source': inventory.source.model_copy(update={'files': {'missing.py': bad}})})
    with pytest.raises(ValueError, match='unique regular file'):
        verify_source_commit(repo, absent)
    (repo/'src/link.py').symlink_to('calculation.py')
    git(repo, 'add', 'src/link.py')
    git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Symlink fixture')
    linked = inventory.model_copy(update={'source': inventory.source.model_copy(update={
        'commit': git(repo, 'rev-parse', 'HEAD'), 'files': {'src/link.py': bad}})})
    with pytest.raises(ValueError, match='regular Git blob'):
        verify_source_commit(repo, linked)


def test_cli_independent_scopes_and_refusal(frozen, monkeypatch, capsys):
    repo, inventory = committed_source(frozen)
    path = repo/'inventory.json'; path.write_text(inventory.model_dump_json())
    launcher = Path(__file__).resolve().parents[2]/'scripts/verify_evidence.py'
    spec = importlib.util.spec_from_file_location('evidence_cli', launcher)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', repo)
    assert module.main(['both', '--inventory', str(path), '--native', '--vendor']) == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result) == {'evidence', 'historical_source'}
    assert module.main(['source-commit', '--inventory', str(path)]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {'historical_source'}
    with pytest.raises(SystemExit) as exc:
        module.main(['source-commit', '--inventory', str(path), '--native'])
    assert exc.value.code == 2
    (repo/'docs/review.md').write_text('tampered')
    with pytest.raises(SystemExit) as exc:
        module.main(['evidence', '--inventory', str(path)])
    assert exc.value.code == 2
    assert 'Verification refused' in capsys.readouterr().err
