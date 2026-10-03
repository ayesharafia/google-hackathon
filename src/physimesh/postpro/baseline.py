"""Read-only baseline verification, separate from physics and review approval (P00.1)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from physimesh.postpro.result_contract import ResultsV1

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Count = Annotated[int, Field(strict=True, ge=0)]
_PACKAGE_MEMBER = re.compile(
    r"(results\.json|run_group\.json|plots/[a-z0-9_]+\.png|"
    r"recipes/[a-z0-9_]+\.json|surfaces/[a-z0-9_]+\.json)"
)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fingerprint(Record):
    sha256: Digest
    bytes: Count


class SourceSnapshot(Record):
    commit: Commit
    files: Annotated[dict[str, Fingerprint], Field(min_length=1)]


class PackageSnapshot(Record):
    data_root: str
    group_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
    manifest: Fingerprint
    files: Annotated[dict[str, Fingerprint], Field(min_length=2)]
    solver_code_commit: Commit
    evidence: Literal["unverified"]
    machine_review: Literal["pending"]


class NativeCase(Record):
    level: Literal["coarse", "medium", "fine"]
    path: str
    record: Fingerprint
    inputs: Annotated[dict[str, Digest], Field(min_length=1)]
    outputs: Annotated[dict[str, Fingerprint], Field(min_length=1)]


class EvidenceRecord(Record):
    """A documentary record; its hash does not prove its assertions independently."""

    name: str
    path: str
    fingerprint: Fingerprint
    status: Literal["recorded"]
    scope: str


class BaselineInventory(Record):
    schema_version: Literal["production_baseline_v1"]
    source: SourceSnapshot
    image_digest: Annotated[str, Field(pattern=r"^[^\s@]+@sha256:[0-9a-f]{64}$")]
    vendor_path: str
    vendor: Fingerprint
    package: PackageSnapshot
    native_cases: Annotated[list[NativeCase], Field(min_length=3, max_length=3)]
    supporting_files: dict[str, Fingerprint]
    records: list[EvidenceRecord]
    claude_reviewed_commit: Commit
    claude_verdict: Literal["pass_bounded_mvp"]
    aircraft_validation: Literal["not_established"]
    human_release_approval: Literal["pending"]
    presentation_rehearsals: Literal["pending"]
    backup_recording: Literal["pending"]
    superseded_roots: list[str]

    @model_validator(mode="after")
    def paths_and_order(self):
        paths = [*self.source.files, self.vendor_path, self.package.data_root,
                 *self.supporting_files, *self.superseded_roots, *(r.path for r in self.records)]
        for case in self.native_cases:
            paths.extend([case.path, *case.inputs, *case.outputs])
        for path in paths:
            relative_path(path)
        for name in self.package.files:
            if not _PACKAGE_MEMBER.fullmatch(name):
                raise ValueError("unsupported package member")
        if not {"results.json", "run_group.json"}.issubset(self.package.files):
            raise ValueError("baseline package requires results and run group")
        if [case.level for case in self.native_cases] != ["coarse", "medium", "fine"]:
            raise ValueError("baseline requires ordered three-mesh records")
        return self


def relative_path(name: str) -> PurePosixPath:
    """Reject traversal, absolute paths and platform-dependent path spellings."""
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or any(ord(c) < 32 for c in name)):
        raise ValueError("expected a safe relative POSIX path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("expected a safe relative POSIX path")
    return path


def confined_file(root: Path, name: str) -> Path:
    path = root.joinpath(*relative_path(name).parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"file escapes verification root: {name}")
    if not path.is_file():
        raise ValueError(f"required file unavailable: {name}")
    return path


def fingerprint(path: Path) -> Fingerprint:
    """Stream native files without loading the full CFD output into memory."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return Fingerprint(sha256=digest.hexdigest(), bytes=size)


def check_file(root: Path, name: str, expected: Fingerprint) -> None:
    if fingerprint(confined_file(root, name)) != expected:
        raise ValueError(f"retained file differs from frozen baseline: {name}")


def read_json(raw: bytes):
    """Ambiguous duplicate keys and nonfinite values cannot select evidence."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"nonfinite JSON value: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def load_inventory(path: Path) -> BaselineInventory:
    return BaselineInventory.model_validate(read_json(path.read_bytes()))


def verify_baseline(repo_root: Path, inventory: BaselineInventory, *,
                    data_root: Path | None = None, native: bool = False,
                    vendor: bool = False) -> dict:
    """Check selected bytes and bindings; never rerun a solver or upgrade evidence.

    data_root may relocate an exact package copy. Native case paths remain relative
    to repo_root. Unchecked scopes are reported explicitly rather than as passes.
    """
    repo_root = repo_root.resolve()
    for name, expected in inventory.source.files.items():
        check_file(repo_root, name, expected)
    for record in inventory.records:
        check_file(repo_root, record.path, record.fingerprint)
    selected = (data_root if data_root is not None
                else repo_root / inventory.package.data_root).resolve()
    package = selected / "results" / inventory.package.group_id
    if not package.resolve().is_relative_to(selected):
        raise ValueError("package escapes selected data root")
    check_file(package, "hashes.json", inventory.package.manifest)
    manifest = read_json((package / "hashes.json").read_bytes())
    expected_manifest = {name: value.sha256 for name, value in inventory.package.files.items()}
    if manifest != expected_manifest:
        raise ValueError("package member hashes differ from frozen inventory")
    present = {p.relative_to(package).as_posix() for p in package.rglob("*")
               if p.is_file() or p.is_symlink()}
    if present != {*expected_manifest, "hashes.json"}:
        raise ValueError("unexpected or missing package members")
    for name, expected in inventory.package.files.items():
        check_file(package, name, expected)
    result = ResultsV1.model_validate(read_json((package / "results.json").read_bytes()))
    group = read_json((package / "run_group.json").read_bytes())
    group_hash = inventory.package.files["run_group.json"].sha256
    if (result.run_group_id != inventory.package.group_id
            or result.provenance.run_group_sha256 != group_hash
            or group_hash[:16] != result.run_group_id
            or result.provenance.image_digest != inventory.image_digest
            or group.get("image_digest") != inventory.image_digest
            or result.provenance.code_version != inventory.package.solver_code_commit
            or group.get("code_version") != inventory.package.solver_code_commit):
        raise ValueError("package provenance differs from frozen baseline")
    for name, expected in inventory.supporting_files.items():
        check_file(selected, name, expected)
    native_count = 0
    if native:
        meshes = group.get("meshes", [])
        if [mesh.get("level") for mesh in meshes] != ["coarse", "medium", "fine"]:
            raise ValueError("native run group requires ordered three-mesh records")
        for case, mesh in zip(inventory.native_cases, meshes, strict=True):
            case_root = repo_root / case.path
            if not case_root.resolve().is_relative_to(repo_root):
                raise ValueError("native case escapes repository")
            check_file(case_root, "run_record.json", case.record)
            record = read_json((case_root / "run_record.json").read_bytes())
            if (mesh.get("state") != "completed"
                    or mesh.get("run_record_sha256") != case.record.sha256
                    or record.get("image_digest") != inventory.image_digest
                    or record.get("inputs") != case.inputs
                    or record.get("outputs") != {n: f.model_dump() for n, f in case.outputs.items()}):
                raise ValueError("native execution provenance differs from frozen baseline")
            for name, digest in case.inputs.items():
                if fingerprint(confined_file(case_root, name)).sha256 != digest:
                    raise ValueError(f"native input hash differs: {name}")
            for name, expected in case.outputs.items():
                check_file(case_root, name, expected)
                native_count += 1
    if vendor:
        check_file(repo_root, inventory.vendor_path, inventory.vendor)
    return {"schema_version": "baseline_verification_v1", "source_commit": inventory.source.commit,
            "source_files_checked": len(inventory.source.files), "package_id": result.run_group_id,
            "package_manifest_sha256": inventory.package.manifest.sha256,
            "package_files_checked": len(inventory.package.files),
            "supporting_files_checked": len(inventory.supporting_files),
            "native_outputs_checked": native_count, "native_checked": native, "vendor_checked": vendor,
            "evidence": result.evidence, "machine_review": result.independent_review,
            "claude_verdict": inventory.claude_verdict, "aircraft_validation": inventory.aircraft_validation,
            "human_release_approval": inventory.human_release_approval,
            "presentation_rehearsals": inventory.presentation_rehearsals,
            "backup_recording": inventory.backup_recording}
