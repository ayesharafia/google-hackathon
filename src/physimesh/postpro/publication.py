"""Content-bound publication identity independent of the frozen ResultsV1 schema.

The payload manifest excludes hashes.json and publication.json to avoid a
self-referential hash. Every other retained member, including recipes, binds
the revision. This is integrity/identity, not reviewer approval or validation.
"""
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SHA = r'^[0-9a-f]{64}$'


class PublicationIdentityV1(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal['publication_identity_v1'] = 'publication_identity_v1'
    study_id: str = Field(pattern=r'^[0-9a-f]{16}$')
    study_sha256: str = Field(pattern=SHA)
    payload_manifest_sha256: str = Field(pattern=SHA)
    package_revision_sha256: str = Field(pattern=SHA)


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def publication_identity(manifest: dict[str, str], study_sha256: str) -> PublicationIdentityV1:
    if not re.fullmatch(SHA, study_sha256):
        raise ValueError('full study digest required')
    payload = {k: v for k, v in manifest.items() if k not in ('hashes.json', 'publication.json')}
    if not {'results.json', 'run_group.json'} <= payload.keys():
        raise ValueError('results and run-group payload members required')
    if any(not isinstance(v, str) or not re.fullmatch(SHA, v) for v in payload.values()):
        raise ValueError('full payload member digests required')
    content = {'schema_version': 'publication_identity_v1', 'study_id': study_sha256[:16],
               'study_sha256': study_sha256, 'payload_manifest_sha256': _digest(payload)}
    return PublicationIdentityV1(**content, package_revision_sha256=_digest(content))


def identity_bytes(identity: PublicationIdentityV1) -> bytes:
    return (json.dumps(identity.model_dump(mode='json'), indent=2, sort_keys=True)+'\n').encode()


def validate_identity(raw: bytes, expected: PublicationIdentityV1) -> None:
    actual = PublicationIdentityV1.model_validate_json(raw)
    if actual != expected:
        raise ValueError('publication envelope differs from verified content')
