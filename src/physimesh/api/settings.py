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
    hosted_mode: bool = False
    database_url: str | None = None
    pool_size: int = 8
    s3_bucket: str | None = None
    s3_endpoint: str | None = None
    s3_region: str | None = None
    allow_local_http_storage: bool = False
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    monitoring_token: str | None = None

    def __post_init__(self) -> None:
        if not self.hosted_mode and (not isinstance(self.api_token, str) or not self.api_token.strip()):
            raise ValueError("PHYSIMESH_API_TOKEN is required")
        if (self.openfoam_image_digest is not None
                and re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", self.openfoam_image_digest) is None):
            raise ValueError("PHYSIMESH_OPENFOAM_IMAGE_DIGEST must be an immutable SHA-256 reference")
        if self.database_url and not self.database_url.startswith(('postgresql://', 'postgres://')):
            raise ValueError('metadata URL must select PostgreSQL')
        if not 1 <= self.pool_size <= 32:
            raise ValueError('metadata pool must contain 1–32 connections')
        oidc = (self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)
        if any(oidc) and not all(oidc):
            raise ValueError('OIDC issuer, audience and JWKS must be configured together')
        if self.s3_bucket and not self.s3_region:
            raise ValueError('private storage requires an explicit region')
        if self.s3_endpoint:
            from urllib.parse import urlparse
            endpoint = urlparse(self.s3_endpoint)
            if endpoint.scheme != 'https' and not (self.allow_local_http_storage
                    and endpoint.scheme == 'http' and endpoint.hostname in ('localhost', '127.0.0.1', '::1')):
                raise ValueError('private storage requires HTTPS; only explicit loopback development can use HTTP')
        if not self.bind_host:
            raise ValueError("PHYSIMESH_BIND_HOST cannot be empty")
        if self.max_upload_bytes <= 0 or self.max_triangles <= 0:
            raise ValueError("STL upload limits must be positive")


def load_settings(env: Mapping[str, str]) -> Settings:
    """Load explicit paths and credentials; missing design/backend values are never guessed."""
    mode = env.get('PHYSIMESH_MODE', 'local')
    if mode not in ('local', 'hosted'):
        raise ValueError('PHYSIMESH_MODE must be local or hosted')
    token = env.get("PHYSIMESH_API_TOKEN", '')
    if not token and mode == 'local':
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
        hosted_mode=mode == 'hosted', database_url=env.get('PHYSIMESH_DATABASE_URL'),
        pool_size=int(env.get('PHYSIMESH_POOL_SIZE', '8')), s3_bucket=env.get('PHYSIMESH_S3_BUCKET'),
        s3_endpoint=env.get('PHYSIMESH_S3_ENDPOINT'), s3_region=env.get('PHYSIMESH_S3_REGION'),
        allow_local_http_storage=env.get('PHYSIMESH_ALLOW_LOCAL_HTTP_STORAGE') == '1',
        oidc_issuer=env.get('PHYSIMESH_OIDC_ISSUER'), oidc_audience=env.get('PHYSIMESH_OIDC_AUDIENCE'),
        oidc_jwks_url=env.get('PHYSIMESH_OIDC_JWKS_URL'), monitoring_token=env.get('PHYSIMESH_MONITORING_TOKEN'),
    )
