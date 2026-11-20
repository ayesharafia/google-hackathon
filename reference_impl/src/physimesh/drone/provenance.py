"""Hashing and provenance records. Implements REQ10 [M§2]."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, NaN/Inf rejected."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_record(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


@dataclass(frozen=True)
class Provenance:
    schema_version: str
    project_snapshot_sha256: str
    code_version: str
    created_utc: str
    geometry_sha256: Optional[str] = None
    mesh_sha256: Optional[str] = None
    backend_name: Optional[str] = None
    backend_version: Optional[str] = None
    backend_image_digest: Optional[str] = None
    recipe_sha256: Optional[str] = None

    def blocking_for_execution(self) -> list:
        """Null backend version or image digest blocks execution [M§32]."""
        missing = []
        if not self.backend_version:
            missing.append("backend_version")
        if not self.backend_image_digest:
            missing.append("backend_image_digest")
        return missing
