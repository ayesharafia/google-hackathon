"""Inspect historical evidence from later checkouts without requalifying physics.

The frozen baseline verifier remains unchanged. Evidence bytes and Git source
bytes are independent scopes; neither executes the historical source or solver.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .baseline import BaselineInventory, check_file, confined_file, fingerprint, read_json, relative_path
from .result_contract import ResultsV1


def verify_evidence(repo_root: Path, inventory: BaselineInventory, *, data_root: Path | None = None,
                    native: bool = False, vendor: bool = False) -> dict:
    """Verify exact retained bytes and documentary bindings, never current source."""
    repo_root = repo_root.resolve()
    for record in inventory.records:
        check_file(repo_root, record.path, record.fingerprint)
    selected = (data_root if data_root is not None else repo_root/inventory.package.data_root).resolve()
    package = selected/'results'/inventory.package.group_id
    if not package.resolve().is_relative_to(selected):
        raise ValueError('package escapes selected data root')
    check_file(package, 'hashes.json', inventory.package.manifest)
    manifest = read_json(confined_file(package, 'hashes.json').read_bytes())
    expected_manifest = {name: value.sha256 for name, value in inventory.package.files.items()}
    if manifest != expected_manifest:
        raise ValueError('package member hashes differ from frozen inventory')
    present = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() or p.is_symlink()}
    if present != {*expected_manifest, 'hashes.json'}:
        raise ValueError('unexpected or missing package members')
    for name, expected in inventory.package.files.items():
        check_file(package, name, expected)
    result = ResultsV1.model_validate(read_json(confined_file(package, 'results.json').read_bytes()))
    group = read_json(confined_file(package, 'run_group.json').read_bytes())
    group_hash = inventory.package.files['run_group.json'].sha256
    if (result.run_group_id != inventory.package.group_id or result.provenance.run_group_sha256 != group_hash
            or group_hash[:16] != result.run_group_id or result.provenance.image_digest != inventory.image_digest
            or group.get('image_digest') != inventory.image_digest
            or result.provenance.code_version != inventory.package.solver_code_commit
            or group.get('code_version') != inventory.package.solver_code_commit):
        raise ValueError('package provenance differs from frozen baseline')
    for name, expected in inventory.supporting_files.items():
        check_file(selected, name, expected)
    native_count = 0
    if native:
        meshes = group.get('meshes', [])
        if [mesh.get('level') for mesh in meshes] != ['coarse', 'medium', 'fine']:
            raise ValueError('native run group requires ordered three-mesh records')
        for case, mesh in zip(inventory.native_cases, meshes, strict=True):
            case_root = repo_root/case.path
            if not case_root.resolve().is_relative_to(repo_root):
                raise ValueError('native case escapes repository')
            check_file(case_root, 'run_record.json', case.record)
            record = read_json(confined_file(case_root, 'run_record.json').read_bytes())
            if (mesh.get('state') != 'completed' or mesh.get('run_record_sha256') != case.record.sha256
                    or record.get('image_digest') != inventory.image_digest or record.get('inputs') != case.inputs
                    or record.get('outputs') != {n: f.model_dump() for n, f in case.outputs.items()}):
                raise ValueError('native execution provenance differs from frozen baseline')
            for name, digest in case.inputs.items():
                if fingerprint(confined_file(case_root, name)).sha256 != digest:
                    raise ValueError('native input hash differs: '+name)
            for name, expected in case.outputs.items():
                check_file(case_root, name, expected)
                native_count += 1
    if vendor:
        check_file(repo_root, inventory.vendor_path, inventory.vendor)
    return {'schema_version': 'retained_evidence_verification_v1',
            'recorded_source_commit': inventory.source.commit, 'current_source_checked': False,
            'package_id': result.run_group_id, 'package_manifest_sha256': inventory.package.manifest.sha256,
            'documentary_records_checked': len(inventory.records),
            'package_files_checked': len(inventory.package.files),
            'supporting_files_checked': len(inventory.supporting_files),
            'native_outputs_checked': native_count, 'native_checked': native, 'vendor_checked': vendor,
            'solver_rerun': False, 'evidence': result.evidence, 'machine_review': result.independent_review,
            'recorded_claude_review': {'commit': inventory.claude_reviewed_commit,
                                     'verdict': inventory.claude_verdict, 'verification': 'document bytes only'},
            'aircraft_validation': inventory.aircraft_validation,
            'human_release_approval': inventory.human_release_approval,
            'qualification': 'Retained evidence identity only. No current-source reproduction, solver execution, '
                             'new physics acceptance or aircraft validation.'}


def git_read(repo_root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(['git', '-C', str(repo_root), *args], check=True, capture_output=True, timeout=15)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError('historical source object unavailable; no source verification accepted') from exc
    return result.stdout


def verify_source_commit(repo_root: Path, inventory: BaselineInventory) -> dict:
    """Read regular Git blobs from the inventory's full commit ID, without checkout."""
    repo_root = repo_root.resolve()
    commit = inventory.source.commit
    resolved = git_read(repo_root, 'rev-parse', '--verify', commit+'^{commit}').decode().strip()
    if resolved != commit:
        raise ValueError('historical source commit identity mismatch')
    for name, expected in inventory.source.files.items():
        relative_path(name)
        tree = git_read(repo_root, 'ls-tree', '-z', '--full-tree', commit, '--', name)
        entries = tree.rstrip(b'\0').split(b'\0')
        if len(entries) != 1 or b'\t' not in entries[0]:
            raise ValueError('historical source path is not a unique regular file: '+name)
        header, path = entries[0].split(b'\t', 1)
        mode, kind, oid = header.decode('ascii').split()
        if mode not in ('100644', '100755') or kind != 'blob' or path.decode() != name:
            raise ValueError('historical source must be a regular Git blob: '+name)
        size = int(git_read(repo_root, 'cat-file', '-s', oid).strip())
        if size != expected.bytes or size > 8_000_000:
            raise ValueError('historical source byte size mismatch or exceeds bounded read: '+name)
        raw = git_read(repo_root, 'cat-file', 'blob', oid)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected.sha256:
            raise ValueError('historical source bytes differ from frozen inventory: '+name)
    return {'schema_version': 'historical_source_verification_v1', 'source_commit': commit,
            'source_files_checked': len(inventory.source.files), 'current_source_checked': False,
            'solver_rerun': False,
            'qualification': 'Exact historical Git source bytes checked. Source was not executed; environment '
                             'and numerical reproduction are not established. Current checkout is not certified.'}
