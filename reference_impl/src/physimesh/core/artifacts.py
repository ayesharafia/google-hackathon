"""Content-addressed, write-once artifact store (plan Task 1.2)."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from typing import BinaryIO


class ArtifactStore:
    def __init__(self, root: pathlib.Path):
        self.root = pathlib.Path(root)
        (self.root / "objects").mkdir(parents=True, exist_ok=True)
        (self.root / "meta").mkdir(parents=True, exist_ok=True)

    def _obj(self, sha: str) -> pathlib.Path:
        return self.root / "objects" / sha[:2] / sha

    def _atomic_write(self, target: pathlib.Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            if target.exists():          # write-once: never overwrite
                os.unlink(tmp)
            else:
                os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def put_bytes(self, data: bytes, *, kind: str, meta: dict) -> str:
        sha = hashlib.sha256(data).hexdigest()
        self._atomic_write(self._obj(sha), data)
        record = {"kind": kind, "size": len(data), **meta}
        self._atomic_write(self.root / "meta" / f"{sha}.json",
                           json.dumps(record, sort_keys=True).encode("utf-8"))
        return sha

    def put_file(self, path: pathlib.Path, *, kind: str, meta: dict) -> str:
        return self.put_bytes(pathlib.Path(path).read_bytes(), kind=kind, meta=meta)

    def open(self, sha256: str) -> BinaryIO:
        p = self._obj(sha256)
        if not p.exists():
            raise KeyError(sha256)
        return p.open("rb")

    def meta(self, sha256: str) -> dict:
        p = self.root / "meta" / f"{sha256}.json"
        if not p.exists():
            raise KeyError(sha256)
        return json.loads(p.read_text(encoding="utf-8"))
