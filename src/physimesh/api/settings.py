"""Explicit environment configuration; unknown backend pins remain null [M§26]."""
from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Server paths, token, immutable image reference, and bind host; no physical units."""

    data_root: pathlib.Path
    db_path: pathlib.Path
    api_token: str
    openfoam_image_digest: str | None
    bind_host: str = "127.0.0.1"  # Private development binding [plan Task 1.5].
    max_upload_bytes: int = 50_000_000
    max_triangles: int = 1_000_000
    local_no_auth: bool = False

    def __post_init__(self) -> None:
        if not self.local_no_auth and (not isinstance(self.api_token, str) or not self.api_token.strip()):
            raise ValueError("PHYSIMESH_API_TOKEN is required")
        if (self.openfoam_image_digest is not None
                and re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", self.openfoam_image_digest) is None):
            raise ValueError("PHYSIMESH_OPENFOAM_IMAGE_DIGEST must be an immutable SHA-256 reference")
        if self.local_no_auth and self.bind_host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("Token-free mode requires a loopback bind host")
        if not self.bind_host:
            raise ValueError("PHYSIMESH_BIND_HOST cannot be empty")
        if self.max_upload_bytes <= 0 or self.max_triangles <= 0:
            raise ValueError("STL upload limits must be positive")


def load_settings(env: Mapping[str, str]) -> Settings:
    """Load explicit paths and credentials; missing design/backend values are never guessed."""
    local_no_auth = env.get("PHYSIMESH_LOCAL_NO_AUTH") == "1"
    token = env.get("PHYSIMESH_API_TOKEN", "")
    if not token and not local_no_auth:
        raise ValueError("PHYSIMESH_API_TOKEN is required; refusing unauthenticated startup")
    root = env.get("PHYSIMESH_DATA_ROOT")
    if not root:
        raise ValueError("PHYSIMESH_DATA_ROOT is required")
    root_path = pathlib.Path(root)
    return Settings(
        root_path,
        pathlib.Path(env.get("PHYSIMESH_DB_PATH", str(root_path / "jobs.sqlite"))),
        token,
        env.get("PHYSIMESH_OPENFOAM_IMAGE_DIGEST") or None,
        env.get("PHYSIMESH_BIND_HOST", "127.0.0.1"),
        int(env.get("PHYSIMESH_MAX_UPLOAD_BYTES", "50000000")),
        int(env.get("PHYSIMESH_MAX_TRIANGLES", "1000000")),
        local_no_auth=local_no_auth,
    )
