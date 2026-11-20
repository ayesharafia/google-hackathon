"""Application settings from PHYSIMESH_* environment variables (plan Task 1.5)."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class Settings:
    data_root: pathlib.Path
    db_path: pathlib.Path
    api_token: str
    openfoam_image_digest: Optional[str]
    bind_host: str = "127.0.0.1"


def load_settings(env: Mapping[str, str]) -> Settings:
    token = env.get("PHYSIMESH_API_TOKEN")
    if not token:
        raise ValueError("PHYSIMESH_API_TOKEN is required; refusing to start without authentication")
    root = env.get("PHYSIMESH_DATA_ROOT")
    if not root:
        raise ValueError("PHYSIMESH_DATA_ROOT is required")
    root_p = pathlib.Path(root)
    return Settings(root_p, pathlib.Path(env.get("PHYSIMESH_DB_PATH", str(root_p / "jobs.sqlite"))),
                    token, env.get("PHYSIMESH_OPENFOAM_IMAGE_DIGEST") or None,
                    env.get("PHYSIMESH_BIND_HOST", "127.0.0.1"))
