"""Offline validation for replacement proposals, not a provider adapter or runner.

This component reads only explicitly requested source files and never mutates
files. It is not an isolation sandbox. It does not verify base_head against live
Git HEAD; the caller must do that separately. Facts are inert, unverified claims.
Requires Python 3.11 and POSIX directory-fd/O_NOFOLLOW support.
"""

import hashlib
import os
import re
import stat
from pathlib import Path


class ProposalInputError(ValueError):
    """Invalid request, snapshot, proposal, or source input."""


_FILE_LIMIT = 128 * 1024
_TOTAL_LIMIT = 512 * 1024
_IDENTITY = {"schema_version", "task_id", "started_at", "base_head"}
_REQUEST = _IDENTITY | {"task_instruction", "sources", "editable_paths"}
_PROPOSAL = _IDENTITY | {"input_hashes", "changes", "facts"}
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _fail(message):
    raise ProposalInputError(message)


def _keys(value, expected, label):
    if type(value) is not dict or value.keys() != expected:
        _fail(label + ": invalid fields")


def _string(value, limit, label):
    if type(value) is not str or not value.strip() or len(value) > limit:
        _fail(label + ": invalid string")
    try:
        value.encode("utf-8", "strict")
    except UnicodeError:
        _fail(label + ": invalid UTF-8")
    if "\x00" in value:
        _fail(label + ": NUL forbidden")
    return value


def _hex(value, pattern, label):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(label + ": invalid hash")
    return value


def _identity(value):
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        _fail("unsupported schema version")
    _string(value["task_id"], 80, "task_id")
    _string(value["started_at"], 80, "started_at")
    _hex(value["base_head"], _HEX40, "base_head")


def _path(value):
    _string(value, 4096, "path")
    if value.startswith("/") or "\\" in value:
        _fail("invalid source path")
    parts = value.split("/")
    for part in parts:
        if part in {"", ".", ".."}:
            _fail("invalid source path")
        lowered = part.lower()
        if (
            lowered in {".git", ".ssh", ".aws", ".codex", "auth.json"}
            or lowered == ".env"
            or lowered.startswith(".env.")
            or any(word in lowered for word in ("credentials", "token", "secrets"))
        ):
            _fail("secret-looking source path")
    return parts


def _hashes(value):
    if type(value) is not dict or not 1 <= len(value) <= 20:
        _fail("invalid source map")
    result = {}
    for path, digest in value.items():
        _path(path)
        result[path] = _hex(digest, _HEX64, "source hash")
    return result


def _editables(value, sources):
    if type(value) is not list or not 1 <= len(value) <= len(sources):
        _fail("invalid editable paths")
    seen = set()
    for path in value:
        _path(path)
        if path not in sources or path in seen:
            _fail("invalid editable paths")
        seen.add(path)
    return list(value)


def _text_bytes(value, label):
    if type(value) is not str:
        _fail(label + ": invalid text")
    if len(value) > _FILE_LIMIT:
        _fail(label + ": oversized")
    try:
        data = value.encode("utf-8", "strict")
    except UnicodeError:
        _fail(label + ": invalid UTF-8")
    if b"\x00" in data:
        _fail(label + ": NUL forbidden")
    if len(data) > _FILE_LIMIT:
        _fail(label + ": oversized")
    return data


def _directory_flags():
    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
    ):
        _fail("safe filesystem access unavailable")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _open_root(root):
    if not isinstance(root, Path) or not root.is_absolute():
        _fail("root must be an absolute directory")
    if root.anchor != "/" or ".." in root.parts:
        _fail("invalid root")
    flags = _directory_flags()
    fd = os.open("/", flags)
    try:
        for part in root.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            _fail("root must be a directory")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_source(root_fd, path):
    parts = _path(path)
    directory_fd = os.dup(root_fd)
    file_fd = None
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, _directory_flags(), dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            _fail("source must be a regular file")
        if metadata.st_size > _FILE_LIMIT:
            _fail("source oversized")
        chunks = []
        size = 0
        while True:
            chunk = os.read(file_fd, min(65536, _FILE_LIMIT + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > _FILE_LIMIT:
                _fail("source oversized")
        data = b"".join(chunks)
        if b"\x00" in data:
            _fail("source contains NUL")
        try:
            text = data.decode("utf-8", "strict")
        except UnicodeError:
            _fail("source is not UTF-8")
        return data, text
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)


def snapshot_inputs(root: Path, request: dict) -> dict:
    """Read and hash requested files; live base HEAD verification is caller-owned."""
    _keys(request, _REQUEST, "request")
    _identity(request)
    _string(request["task_instruction"], 16000, "task_instruction")
    hashes = _hashes(request["sources"])
    editables = _editables(request["editable_paths"], hashes)
    sources = {}
    total = 0
    root_fd = None
    try:
        root_fd = _open_root(root)
        for path, expected in hashes.items():
            data, text = _read_source(root_fd, path)
            total += len(data)
            if total > _TOTAL_LIMIT:
                _fail("sources exceed total limit")
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                _fail("source hash mismatch")
            sources[path] = {"text": text, "sha256": actual}
    except OSError:
        raise ProposalInputError("safe source access failed") from None
    finally:
        if root_fd is not None:
            os.close(root_fd)
    return {
        "schema_version": 1,
        "task_id": request["task_id"],
        "started_at": request["started_at"],
        "base_head": request["base_head"],
        "task_instruction": request["task_instruction"],
        "sources": sources,
        "editable_paths": editables,
    }


def _snapshot_hashes(snapshot):
    _keys(snapshot, _REQUEST, "snapshot")
    _identity(snapshot)
    _string(snapshot["task_instruction"], 16000, "task_instruction")
    sources = snapshot["sources"]
    if type(sources) is not dict or not 1 <= len(sources) <= 20:
        _fail("invalid snapshot sources")
    hashes = {}
    total = 0
    for path, source in sources.items():
        _path(path)
        _keys(source, {"text", "sha256"}, "snapshot source")
        digest = _hex(source["sha256"], _HEX64, "snapshot hash")
        data = _text_bytes(source["text"], "snapshot source")
        total += len(data)
        if total > _TOTAL_LIMIT:
            _fail("snapshot exceeds total limit")
        if hashlib.sha256(data).hexdigest() != digest:
            _fail("snapshot hash mismatch")
        hashes[path] = digest
    _editables(snapshot["editable_paths"], hashes)
    return hashes


def validate_proposal(snapshot: dict, proposal: dict) -> dict:
    """Validate full-file replacements without interpreting diffs or applying edits.

    Snapshot integrity is checked, but its provenance and live base HEAD remain
    the caller's responsibility. Returned facts have no authority.
    """
    hashes = _snapshot_hashes(snapshot)
    _keys(proposal, _PROPOSAL, "proposal")
    _identity(proposal)
    for key in _IDENTITY:
        if proposal[key] != snapshot[key]:
            _fail("proposal identity mismatch")
    if _hashes(proposal["input_hashes"]) != hashes:
        _fail("proposal input hashes mismatch")

    changes = proposal["changes"]
    if type(changes) is not list or not 1 <= len(changes) <= 20:
        _fail("invalid changes")
    editable = set(snapshot["editable_paths"])
    seen = set()
    normalized = []
    total = 0
    for change in changes:
        _keys(change, {"path", "before_sha256", "after_text"}, "change")
        path = change["path"]
        _path(path)
        if path not in editable or path in seen:
            _fail("invalid change path")
        before = _hex(change["before_sha256"], _HEX64, "before hash")
        if before != hashes[path]:
            _fail("before hash mismatch")
        data = _text_bytes(change["after_text"], "replacement")
        total += len(data)
        if total > _TOTAL_LIMIT:
            _fail("replacements exceed total limit")
        seen.add(path)
        normalized.append({
            "path": path,
            "before_sha256": before,
            "after_text": change["after_text"],
        })

    facts = proposal["facts"]
    if type(facts) is not list or len(facts) > 20:
        _fail("invalid facts")
    for fact in facts:
        _string(fact, 2000, "fact")
    return {"changes": normalized, "facts": list(facts)}
