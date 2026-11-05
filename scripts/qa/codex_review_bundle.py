"""Offline importer and review packager for preexisting snapshots and proposals.

Uses the existing proposal validator. Does not verify live HEAD, approval,
snapshot provenance, authority, or current state. Facts are inert, unverified
claims. Snapshots intentionally contain source text; no secret redaction is
claimed. Diffs are representations only and are never applied.

Requires Python 3.11 and POSIX directory-fd, O_NOFOLLOW, and hard-link support.
Invoke with: python -m scripts.qa.codex_review_bundle
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import stat
import sys
from typing import Any

from scripts.qa.codex_proposal_inputs import (
    ProposalInputError,
    validate_proposal,
)

_INPUT_LIMIT = 2 * 1024 * 1024
_ARTIFACT_LIMIT = 8 * 1024 * 1024
_BUNDLE_LIMIT = 32 * 1024 * 1024
_FIXED_NAMES = {
    "request-snapshot.json",
    "proposal.json",
    "changes.json",
    "proposal.diff",
    "facts.json",
    "result.json",
    "bundle.json",
}
_REPLACEMENT = re.compile(r"replacements/([0-9]{3})\.txt\Z")
_TEMP_MANIFEST = ".bundle.json.tmp"


class BundleInputError(ValueError):
    """Invalid offline input."""


class BundlePublicationError(ValueError):
    """Bundle publication failed."""


def _reject(message: str = "invalid_input") -> None:
    raise BundleInputError(message)


def _check_json(value: Any, depth: int = 0) -> None:
    if depth > 64:
        _reject()
    kind = type(value)
    if value is None or kind in (str, bool, int, float):
        return
    if kind is list:
        for item in value:
            _check_json(item, depth + 1)
        return
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str:
                _reject()
            _check_json(item, depth + 1)
        return
    _reject()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _constant(_: str) -> None:
    _reject()


def _decode(data: bytes) -> Any:
    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
        _check_json(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise BundleInputError("invalid_input") from None


def _canonical(value: Any, limit: int = _ARTIFACT_LIMIT) -> bytes:
    try:
        _check_json(value)
        data = (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8", "strict")
        if len(data) > limit:
            _reject()
        decoded = _decode(data)
        again = (
            json.dumps(
                decoded,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8", "strict")
        if again != data:
            _reject()
        return data
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise BundleInputError("invalid_input") from None


def _metadata() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "offline_review_bundle",
        "status": "review_required",
        "completion_allowed": False,
        "provider_invoked": False,
        "authority_verified": False,
        "head_verified": False,
        "approval_verified": False,
        "current_state_verified": False,
        "snapshot_provenance_verified": False,
        "facts_verified": False,
        "facts_inert": True,
        "diff_representational_only": True,
        "source_text_included": True,
        "secret_redaction_claimed": False,
        "verification_notice": (
            "Offline packaging does not verify live HEAD, approval, current "
            "state, authority, or snapshot provenance. Facts are inert, "
            "unverified claims. Snapshot source text is included."
        ),
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_bundle(snapshot: dict, proposal: dict) -> dict[str, bytes]:
    """Validate and package detached JSON copies without filesystem access."""
    snapshot_bytes = _canonical(snapshot, _INPUT_LIMIT)
    proposal_bytes = _canonical(proposal, _INPUT_LIMIT)
    snapshot_copy = _decode(snapshot_bytes)
    proposal_copy = _decode(proposal_bytes)
    try:
        validated = validate_proposal(snapshot_copy, proposal_copy)
    except ProposalInputError:
        raise BundleInputError("invalid_input") from None

    artifacts: dict[str, bytes] = {
        "request-snapshot.json": snapshot_bytes,
        "proposal.json": proposal_bytes,
    }
    changes = []
    diff_parts = []
    for index, change in enumerate(validated["changes"]):
        path = change["path"]
        after = change["after_text"].encode("utf-8", "strict")
        artifact = f"replacements/{index:03d}.txt"
        artifacts[artifact] = after
        changes.append({
            "path": path,
            "before_sha256": change["before_sha256"],
            "after_sha256": _sha256(after),
            "bytes": len(after),
            "artifact": artifact,
        })
        before_text = snapshot_copy["sources"][path]["text"]
        # JSON labels keep embedded path control characters off header lines.
        label = json.dumps(path, ensure_ascii=True)
        for line in difflib.unified_diff(
            before_text.splitlines(keepends=True),
            change["after_text"].splitlines(keepends=True),
            fromfile="snapshot/" + label,
            tofile="proposal/" + label,
            lineterm="\n",
        ):
            diff_parts.append(line)
            if not line.endswith("\n"):
                diff_parts.append("\n\\ No newline at end of file\n")

    artifacts["changes.json"] = _canonical({
        "schema_version": 1,
        "changes": changes,
    })
    artifacts["proposal.diff"] = "".join(diff_parts).encode("utf-8", "strict")
    artifacts["facts.json"] = _canonical({
        "schema_version": 1,
        "inert": True,
        "verified": False,
        "facts": validated["facts"],
    })
    artifacts["result.json"] = _canonical(_metadata())
    if any(len(data) > _ARTIFACT_LIMIT for data in artifacts.values()):
        _reject()
    manifest = _metadata()
    manifest["artifacts"] = {
        name: {"sha256": _sha256(data), "bytes": len(data)}
        for name, data in sorted(artifacts.items())
    }
    artifacts["bundle.json"] = _canonical(manifest)
    if sum(map(len, artifacts.values())) > _BUNDLE_LIMIT:
        _reject()
    return artifacts


def _absolute_path(path: Any) -> str:
    try:
        raw = os.fspath(path)
        if type(raw) is not str or not raw or "\x00" in raw:
            _reject()
        if ".." in raw.split("/"):
            _reject()
        normalized = os.path.abspath(raw)
        if not normalized.startswith("/") or normalized.startswith("//"):
            _reject()
        normalized.encode("utf-8", "strict")
        return normalized
    except (TypeError, ValueError, UnicodeError, OSError):
        raise BundleInputError("invalid_input") from None


def _directory_flags() -> int:
    if (
        os.name != "posix"
        or not all(hasattr(os, name) for name in (
            "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"
        ))
        or os.open not in os.supports_dir_fd
    ):
        _reject()
    return (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        | os.O_NONBLOCK | os.O_CLOEXEC
    )


def _open_directory(path: str) -> int:
    flags = _directory_flags()
    fd = os.open("/", flags)
    try:
        for component in path.split("/")[1:]:
            if not component:
                continue
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            _reject()
        return fd
    except BaseException:
        os.close(fd)
        raise


def strict_load(path: Any, limit: int) -> Any:
    """Read bounded UTF-8 JSON through an anchored, symlink-free path."""
    if type(limit) is not int or not 0 < limit <= _INPUT_LIMIT:
        _reject()
    normalized = _absolute_path(path)
    parent, name = os.path.split(normalized)
    if not name:
        _reject()
    parent_fd = None
    file_fd = None
    try:
        parent_fd = _open_directory(parent)
        file_fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            _reject()
        chunks = []
        size = 0
        while True:
            chunk = os.read(file_fd, min(65536, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                _reject()
            chunks.append(chunk)
        value = _decode(b"".join(chunks))
        _canonical(value, limit)
        return value
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise BundleInputError("invalid_input") from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _checked_artifacts(artifacts: Any) -> dict[str, bytes]:
    if type(artifacts) is not dict:
        raise BundlePublicationError("publication_error")
    copied = {}
    indexes = []
    for name, data in artifacts.items():
        if type(name) is not str or type(data) is not bytes:
            raise BundlePublicationError("publication_error")
        if name not in _FIXED_NAMES:
            match = _REPLACEMENT.fullmatch(name)
            if match is None:
                raise BundlePublicationError("publication_error")
            indexes.append(int(match.group(1)))
        if len(data) > _ARTIFACT_LIMIT:
            raise BundlePublicationError("publication_error")
        copied[name] = data
    if (
        not _FIXED_NAMES.issubset(copied)
        or not 1 <= len(indexes) <= 20
        or sorted(indexes) != list(range(len(indexes)))
        or sum(map(len, copied.values())) > _BUNDLE_LIMIT
    ):
        raise BundlePublicationError("publication_error")
    try:
        manifest = _decode(copied["bundle.json"])
        expected = _metadata()
        expected["artifacts"] = {
            name: {"sha256": _sha256(data), "bytes": len(data)}
            for name, data in sorted(copied.items())
            if name != "bundle.json"
        }
        if copied["bundle.json"] != _canonical(expected) or manifest != expected:
            raise BundlePublicationError("publication_error")
    except BundleInputError:
        raise BundlePublicationError("publication_error") from None
    return copied


def _write_file(directory_fd: int, name: str, data: bytes) -> None:
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("write_failed")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def write_bundle(output: Any, artifacts: dict[str, bytes]) -> None:
    """Publish into an exclusively created directory; leave failures incomplete.

    The parent must already exist without symlink components. Directory creation
    is not atomic publication. bundle.json is the last completion marker.
    """
    parent_fd = output_fd = replacements_fd = None
    linked = False
    finalized = False
    try:
        checked = _checked_artifacts(artifacts)
        normalized = _absolute_path(output)
        parent, name = os.path.split(normalized)
        if not name:
            raise BundlePublicationError("publication_error")
        parent_fd = _open_directory(parent)
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        output_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
        os.fchmod(output_fd, 0o700)
        os.mkdir("replacements", mode=0o700, dir_fd=output_fd)
        replacements_fd = os.open(
            "replacements", _directory_flags(), dir_fd=output_fd
        )
        os.fchmod(replacements_fd, 0o700)
        for artifact, data in sorted(checked.items()):
            if artifact == "bundle.json":
                continue
            if artifact.startswith("replacements/"):
                _write_file(replacements_fd, artifact.split("/")[1], data)
            else:
                _write_file(output_fd, artifact, data)
        os.fsync(replacements_fd)
        os.fsync(output_fd)
        os.fsync(parent_fd)
        _write_file(output_fd, _TEMP_MANIFEST, checked["bundle.json"])
        os.link(
            _TEMP_MANIFEST,
            "bundle.json",
            src_dir_fd=output_fd,
            dst_dir_fd=output_fd,
            follow_symlinks=False,
        )
        linked = True
        os.unlink(_TEMP_MANIFEST, dir_fd=output_fd)
        os.fsync(output_fd)
        finalized = True
    except (OSError, ValueError, TypeError):
        raise BundlePublicationError("publication_error") from None
    finally:
        if linked and not finalized and output_fd is not None:
            try:
                os.unlink("bundle.json", dir_fd=output_fd)
                os.fsync(output_fd)
            except OSError:
                pass
        for fd in (replacements_fd, output_fd, parent_fd):
            if fd is not None:
                os.close(fd)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BundleInputError("invalid_input")


def _report(status: str, error: str | None = None) -> None:
    value = {"status": status}
    if error is not None:
        value["error"] = error
    sys.stdout.write(_canonical(value, 1024).decode("utf-8"))
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(allow_abbrev=False, add_help=False)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--output-dir", required=True)
    try:
        arguments = list(sys.argv[1:] if argv is None else argv)
        for option in ("--snapshot", "--proposal", "--output-dir"):
            occurrences = sum(
                item == option or item.startswith(option + "=")
                for item in arguments
            )
            if occurrences != 1:
                _reject()
        args = parser.parse_args(arguments)
        snapshot_path = _absolute_path(args.snapshot)
        proposal_path = _absolute_path(args.proposal)
        output_path = _absolute_path(args.output_dir)
        snapshot = strict_load(snapshot_path, _INPUT_LIMIT)
        proposal = strict_load(proposal_path, _INPUT_LIMIT)
        artifacts = build_bundle(snapshot, proposal)
    except Exception:  # noqa: BLE001 - CLI boundary must not print source-bearing errors.
        _report("invalid_input", "invalid_input")
        return 2
    try:
        write_bundle(output_path, artifacts)
    except Exception:  # noqa: BLE001 - CLI boundary must not print source-bearing errors.
        _report("publication_error", "publication_error")
        return 3
    _report("finalized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
