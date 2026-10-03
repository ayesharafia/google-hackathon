"""Baseline identity, portability and refusal behavior; no aircraft-physics claims."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from physimesh.postpro.baseline import (
    BaselineInventory,
    fingerprint,
    load_inventory,
    read_json,
    verify_baseline,
)
from physimesh.postpro.result_contract import assemble_results

IMAGE = "opencfd/openfoam-run@sha256:" + "b" * 64


def write(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return fingerprint(path).model_dump()


@pytest.fixture
def frozen(tmp_path):
    repo = tmp_path / "repo"
    source = write(repo, "src/calculation.py", b"# frozen model\n")
    vendor = write(repo, "vendor/archive.tgz", b"vendor fixture")
    doc = write(repo, "docs/review.md", b"bounded fixture review; no validation\n")
    cases, meshes = [], []
    for level in ("coarse", "medium", "fine"):
        root = repo / "native" / level
        command = write(root, "system/controlDict", b"fixed fixture")
        output = write(root, "fields/value", b"native fixture")
        record = {"image_digest": IMAGE, "inputs": {"system/controlDict": command["sha256"]},
                  "outputs": {"fields/value": output}}
        record_hash = write(root, "run_record.json", json.dumps(record).encode())
        cases.append({"level": level, "path": f"native/{level}", "record": record_hash,
                      "inputs": record["inputs"], "outputs": record["outputs"]})
        meshes.append({"level": level, "state": "completed", "run_record_sha256": record_hash["sha256"]})
    group = {"label": "VERIFICATION CASE: fixture", "code_version": "a" * 40, "image_digest": IMAGE,
             "Re": 100, "D_m": 1, "rho_ref_kg_m3": 1, "nu_m2_s": .01,
             "u_inf_m_s": [1, 0, 0], "meshes": meshes}
    raw_group = json.dumps(group).encode()
    digest = hashlib.sha256(raw_group).hexdigest()
    loads = {"run_group_sha256": digest, "runs": [
        {"level": level, "cd": 1.1, "reconciliation": {"status": "diagnostic_only"},
         "convergence": {"passed": True}} for level in ("coarse", "medium", "fine")],
        "mesh_study": {"behaviour": "oscillatory"}}
    result = assemble_results(group, loads, [])
    data = repo / "data"
    package = data / "results" / digest[:16]
    files = {"run_group.json": write(package, "run_group.json", raw_group),
             "results.json": write(package, "results.json", json.dumps(result).encode()),
             "plots/pressure.png": write(package, "plots/pressure.png", b"plot fixture")}
    manifest = write(package, "hashes.json", json.dumps({n: f["sha256"] for n, f in files.items()}).encode())
    supporting = write(data, "examples/screening.json", b'{"label":"synthetic fixture"}')
    inventory = BaselineInventory.model_validate({
        "schema_version": "production_baseline_v1", "source": {"commit": "c" * 40,
            "files": {"src/calculation.py": source}}, "image_digest": IMAGE,
        "vendor_path": "vendor/archive.tgz", "vendor": vendor,
        "package": {"data_root": "data", "group_id": digest[:16], "manifest": manifest,
                    "files": files, "solver_code_commit": "a" * 40,
                    "evidence": "unverified", "machine_review": "pending"},
        "native_cases": cases, "supporting_files": {"examples/screening.json": supporting},
        "records": [{"name": "fixture review", "path": "docs/review.md", "fingerprint": doc,
                     "status": "recorded", "scope": "fixture only"}],
        "claude_reviewed_commit": "d" * 40, "claude_verdict": "pass_bounded_mvp",
        "aircraft_validation": "not_established", "human_release_approval": "pending",
        "presentation_rehearsals": "pending", "backup_recording": "pending", "superseded_roots": ["old-data"],
    })
    return repo, data, package, inventory


def test_full_verification_reports_scopes_without_promoting_evidence(frozen):
    repo, _, _, inventory = frozen
    report = verify_baseline(repo, inventory, native=True, vendor=True)
    assert report["native_outputs_checked"] == 3
    assert report["native_checked"] and report["vendor_checked"]
    assert report["evidence"] == "unverified" and report["machine_review"] == "pending"
    assert report["aircraft_validation"] == "not_established"
    minimal = verify_baseline(repo, inventory)
    assert not minimal["native_checked"] and not minimal["vendor_checked"]


@pytest.mark.parametrize("name", ["results.json", "plots/pressure.png", "run_group.json"])
def test_tampered_package_member_is_refused(frozen, name):
    repo, _, package, inventory = frozen
    (package / name).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        verify_baseline(repo, inventory)


def test_rehashed_historical_revision_with_same_study_id_is_refused(frozen, tmp_path):
    import shutil

    repo, data, _, inventory = frozen
    old = tmp_path / "historical"
    shutil.copytree(data, old)
    package = old / "results" / inventory.package.group_id
    result = json.loads((package / "results.json").read_text())
    result["interpretation"] = [{"text": "superseded estimate"}]
    (package / "results.json").write_text(json.dumps(result))
    hashes = json.loads((package / "hashes.json").read_text())
    hashes["results.json"] = fingerprint(package / "results.json").sha256
    (package / "hashes.json").write_text(json.dumps(hashes))
    with pytest.raises(ValueError, match="hashes.json"):
        verify_baseline(repo, inventory, data_root=old)


@pytest.mark.parametrize("name", ["src/calculation.py", "docs/review.md", "data/examples/screening.json"])
def test_changed_source_record_or_example_is_refused(frozen, name):
    repo, _, _, inventory = frozen
    (repo / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs from frozen baseline"):
        verify_baseline(repo, inventory)


@pytest.mark.parametrize("name", ["system/controlDict", "fields/value", "run_record.json"])
def test_native_input_output_or_record_tampering_is_refused(frozen, name):
    repo, _, _, inventory = frozen
    (repo / "native/coarse" / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="(hash differs|differs from frozen baseline)"):
        verify_baseline(repo, inventory, native=True)


def test_vendor_tampering_checked_only_when_requested(frozen):
    repo, _, _, inventory = frozen
    (repo / "vendor/archive.tgz").write_bytes(b"changed")
    verify_baseline(repo, inventory)
    with pytest.raises(ValueError, match="archive.tgz"):
        verify_baseline(repo, inventory, vendor=True)


def test_relocated_package_and_repository_verify_without_original_absolute_paths(frozen, tmp_path):
    import shutil

    repo, data, _, inventory = frozen
    moved_repo = tmp_path / "another-checkout"
    moved_data = tmp_path / "separate-retained-evidence"
    shutil.copytree(repo, moved_repo)
    shutil.copytree(data, moved_data)
    shutil.rmtree(repo)
    report = verify_baseline(moved_repo, inventory, data_root=moved_data, native=True)
    assert report["package_files_checked"] == 3


def test_extra_or_escaped_member_is_refused(frozen, tmp_path):
    repo, _, package, inventory = frozen
    extra = package / "unlisted.json"
    extra.write_bytes(b"unlisted")
    with pytest.raises(ValueError, match="unexpected"):
        verify_baseline(repo, inventory)
    extra.unlink()
    outside = tmp_path / "outside.png"
    outside.write_bytes((package / "plots/pressure.png").read_bytes())
    (package / "plots/pressure.png").unlink()
    (package / "plots/pressure.png").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        verify_baseline(repo, inventory)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../b", "a\\b", "a//b", "./a"])
def test_unsafe_inventory_paths_are_rejected(frozen, name):
    inventory = frozen[-1].model_dump()
    inventory["source"]["files"] = {name: next(iter(inventory["source"]["files"].values()))}
    with pytest.raises(ValueError, match="relative POSIX"):
        BaselineInventory.model_validate(inventory)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_ambiguous_json_cannot_select_a_baseline(raw):
    with pytest.raises(ValueError):
        read_json(raw)


def test_inventory_roundtrip_and_no_status_upgrade(frozen, tmp_path):
    inventory = frozen[-1]
    path = tmp_path / "inventory.json"
    path.write_text(inventory.model_dump_json())
    assert load_inventory(path) == inventory
    changed = inventory.model_dump()
    changed["human_release_approval"] = "approved"
    with pytest.raises(ValueError):
        BaselineInventory.model_validate(changed)


def test_demo_preset_checks_before_launch_and_never_prints_token(frozen, tmp_path, monkeypatch, capsys):
    repo, data, _, inventory = frozen
    spec = importlib.util.spec_from_file_location("baseline_cli", Path(__file__).parents[2] / "scripts/verify_baseline.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    path = tmp_path / "inventory.json"
    path.write_text(inventory.model_dump_json())
    preset = tmp_path / "preset.json"
    preset.write_text(json.dumps({"schema_version": "reviewed_demo_v1", "inventory_sha256": fingerprint(path).sha256}))
    monkeypatch.setattr(cli, "ROOT", repo)
    monkeypatch.setattr(cli, "DEFAULT_INVENTORY", path)
    monkeypatch.setenv("PHYSIMESH_API_TOKEN", "private-session-token")
    monkeypatch.setenv("PHYSIMESH_DATA_ROOT", "/wrong/root")
    monkeypatch.setenv("PHYSIMESH_BIND_HOST", "0.0.0.0")
    calls = []
    monkeypatch.setattr(cli.subprocess, "call", lambda argv, **kw: calls.append((argv, kw)) or 0)
    assert cli.main(["demo", "--preset", str(preset), "--check-only"]) == 0
    assert not calls
    assert cli.main(["demo", "--preset", str(preset)]) == 0
    argv, kw = calls[0]
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert kw["env"]["PHYSIMESH_DATA_ROOT"] == str(data)
    assert kw["env"]["PHYSIMESH_OPENFOAM_IMAGE_DIGEST"] == IMAGE
    assert "private-session-token" not in capsys.readouterr().out
    other_group = data / "results" / ("0" * 16)
    other_group.mkdir()
    with pytest.raises(SystemExit) as error:
        cli.main(["demo", "--preset", str(preset), "--check-only"])
    assert error.value.code == 2 and len(calls) == 1
    other_group.rmdir()
    (data / "examples/screening.json").write_bytes(b"changed")
    with pytest.raises(SystemExit) as error:
        cli.main(["demo", "--preset", str(preset)])
    assert error.value.code == 2 and len(calls) == 1
