"""Content-addressed, write-once artifact store (plan Task 1.2)."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import tempfile
from typing import BinaryIO


class ArtifactStore:
    """Retain immutable bytes and first-write metadata [M§26]. Sizes are bytes."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        (self.root / "objects").mkdir(parents=True, exist_ok=True)
        (self.root / "meta").mkdir(parents=True, exist_ok=True)

    def _obj(self, sha: str) -> pathlib.Path:
        self._validate_digest(sha)
        return self.root / "objects" / sha[:2] / sha

    @staticmethod
    def _validate_digest(sha: str) -> None:
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None:
            raise ValueError("artifact ID must be a lowercase SHA-256 digest")

    @staticmethod
    def _sync_directory(path: pathlib.Path) -> None:
        """Persist directory entries on POSIX; Windows supports local development only.

        Windows has no portable directory fsync through Python's os API. File
        fsync, atomic hard-link publication and existing-byte verification still
        apply there, but power-loss durability of directory entries is unqualified.
        """
        if os.name == "nt":
            return
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _atomic_write(self, target: pathlib.Path, data: bytes, *, verify_existing: bool = False) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Persist a newly created object shard before acknowledging retention.
        self._sync_directory(target.parent.parent)
        fd, tmp = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            # Atomic first-write publication avoids replace's overwrite race [ASSUMPTION].
            try:
                os.link(tmp, target)
            except FileExistsError:
                if verify_existing:
                    with target.open("rb") as retained:
                        if retained.read(len(data) + 1) != data:
                            raise ValueError("retained artifact byte integrity failed")
            os.unlink(tmp)
            self._sync_directory(target.parent)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def put_bytes(self, data: bytes, *, kind: str, meta: dict) -> str:
        """Store bytes and metadata, returning their SHA-256; first metadata wins."""
        record = {**meta, "kind": kind, "size": len(data)}
        encoded = json.dumps(record, sort_keys=True, allow_nan=False).encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        self._atomic_write(self._obj(sha), data, verify_existing=True)
        self._atomic_write(self.root / "meta" / f"{sha}.json",
                           encoded)
        return sha

    def put_file(self, path: pathlib.Path, *, kind: str, meta: dict) -> str:
        """Retain a file's bytes without changing the original file."""
        return self.put_bytes(pathlib.Path(path).read_bytes(), kind=kind, meta=meta)

    def open(self, sha256: str) -> BinaryIO:
        """Open retained bytes for reading; missing objects raise KeyError."""
        p = self._obj(sha256)
        if not p.exists():
            raise KeyError(sha256)
        return p.open("rb")

    def meta(self, sha256: str) -> dict:
        """Return original metadata, including byte size and artifact kind."""
        self._validate_digest(sha256)
        p = self.root / "meta" / f"{sha256}.json"
        if not p.exists():
            raise KeyError(sha256)
        return json.loads(p.read_text(encoding="utf-8"))
