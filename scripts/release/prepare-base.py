"""Bind an offline OCI context to a registry-verified immutable base."""

import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
import tempfile
import zlib
from pathlib import Path

MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_INDEX_DEPTH = 4

OCI_INDEX = "application/vnd.oci.image.index.v1+json"
DOCKER_INDEX = "application/vnd.docker.distribution.manifest.list.v2+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
DOCKER_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
OCI_CONFIG = "application/vnd.oci.image.config.v1+json"
DOCKER_CONFIG = "application/vnd.docker.container.image.v1+json"

INDEX_TYPES = {OCI_INDEX, DOCKER_INDEX}
MANIFEST_TYPES = {OCI_MANIFEST, DOCKER_MANIFEST}
LAYER_TYPES = {
    OCI_MANIFEST: {
        "application/vnd.oci.image.layer.v1.tar",
        "application/vnd.oci.image.layer.v1.tar+gzip",
        "application/vnd.oci.image.layer.v1.tar+zstd",
        "application/vnd.oci.image.layer.nondistributable.v1.tar",
        "application/vnd.oci.image.layer.nondistributable.v1.tar+gzip",
        "application/vnd.oci.image.layer.nondistributable.v1.tar+zstd",
    },
    DOCKER_MANIFEST: {
        "application/vnd.docker.image.rootfs.diff.tar.gzip",
        "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip",
    },
}
DIGEST_RE = re.compile(r"sha256:[a-f0-9]{64}")
PATH_COMPONENT_RE = re.compile(
    r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
)
HOST_RE = re.compile(
    r"[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)*"
)


def _digest(value: object) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise ValueError("invalid SHA256 digest")
    return value


def _immutable_ref(base: str) -> tuple[str, str]:
    if not isinstance(base, str) or base.count("@") != 1:
        raise ValueError("an immutable base digest is required")
    repository, digest = base.split("@")
    _digest(digest)
    parts = repository.split("/")
    if not repository or any(not part for part in parts):
        raise ValueError("invalid immutable repository reference")

    first = parts[0]
    if len(parts) > 1 and (
        "." in first or ":" in first or first == "localhost"
    ):
        host, separator, port = first.partition(":")
        if HOST_RE.fullmatch(host) is None:
            raise ValueError("invalid registry host")
        if separator and (
            not port.isascii()
            or not port.isdigit()
            or not 1 <= int(port) <= 65535
        ):
            raise ValueError("invalid registry port")
        parts = parts[1:]

    last, separator, tag = parts[-1].partition(":")
    if separator:
        if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag) is None:
            raise ValueError("invalid immutable reference tag")
        parts[-1] = last
    if any(PATH_COMPONENT_RE.fullmatch(part) is None for part in parts):
        raise ValueError("invalid immutable repository reference")
    return repository, digest


def _json(raw: bytes | str) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise ValueError("invalid JSON constant: " + value)

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(
        raw, object_pairs_hook=pairs, parse_constant=invalid_constant
    )


def _descriptor(value: object, allowed_media: set[str]) -> dict:
    if not isinstance(value, dict):
        raise TypeError("invalid registry descriptor")
    media = value.get("mediaType")
    if not isinstance(media, str) or media not in allowed_media:
        raise ValueError("unsupported descriptor media type")
    _digest(value.get("digest"))
    size = value.get("size")
    if type(size) is not int or size < 0:
        raise ValueError("invalid descriptor size")
    return value


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def verified_registry_config(base: str) -> str:
    """Return the config digest authenticated by an immutable registry reference."""
    repository, root_digest = _immutable_ref(base)

    def visit(
        digest: str, descriptor: dict | None, depth: int
    ) -> str:
        reference = repository + "@" + digest
        raw = subprocess.check_output(
            ["docker", "buildx", "imagetools", "inspect", "--raw", reference]
        )
        if not isinstance(raw, bytes):
            raise TypeError("registry inspection must return bytes")
        if len(raw) > MAX_MEMBER_BYTES:
            raise ValueError("registry manifest exceeds size limit")
        if _sha256(raw) != digest:
            raise ValueError("registry manifest digest mismatch")
        if descriptor is not None and len(raw) != descriptor["size"]:
            raise ValueError("registry descriptor size mismatch")

        document = _json(raw)
        if not isinstance(document, dict):
            raise TypeError("invalid registry manifest")
        if (
            type(document.get("schemaVersion")) is not int
            or document["schemaVersion"] != 2
        ):
            raise ValueError("registry manifest must use schema version 2")
        media = document.get("mediaType")
        if not isinstance(media, str) or media not in INDEX_TYPES | MANIFEST_TYPES:
            raise ValueError("unsupported registry manifest media type")
        if descriptor is not None and media != descriptor["mediaType"]:
            raise ValueError("registry descriptor media type mismatch")

        if media in INDEX_TYPES:
            if depth >= MAX_INDEX_DEPTH:
                raise ValueError("registry index depth limit exceeded")
            manifests = document.get("manifests")
            if not isinstance(manifests, list) or not manifests:
                raise ValueError("invalid registry index")
            candidates = []
            for entry in manifests:
                entry = _descriptor(entry, INDEX_TYPES | MANIFEST_TYPES)
                platform = entry.get("platform")
                if platform is not None:
                    if not isinstance(platform, dict):
                        raise ValueError("invalid descriptor platform")
                    if (
                        not isinstance(platform.get("os"), str)
                        or not isinstance(platform.get("architecture"), str)
                    ):
                        raise ValueError("invalid descriptor platform")
                    if "variant" in platform and not isinstance(
                        platform["variant"], str
                    ):
                        raise ValueError("invalid descriptor variant")
                    if (
                        platform["os"] == "linux"
                        and platform["architecture"] == "amd64"
                    ):
                        if "variant" in platform and platform["variant"] != "v1":
                            raise ValueError("unsupported linux/amd64 variant")
                        candidates.append(entry)
            if len(candidates) != 1:
                raise ValueError("registry index must select exactly one linux/amd64 image")
            selected = candidates[0]
            return visit(selected["digest"], selected, depth + 1)

        config_media = OCI_CONFIG if media == OCI_MANIFEST else DOCKER_CONFIG
        config = _descriptor(document.get("config"), {config_media})
        layers = document.get("layers")
        if not isinstance(layers, list):
            raise TypeError("invalid registry manifest layers")
        for layer in layers:
            _descriptor(layer, LAYER_TYPES[media])
        return config["digest"]

    return visit(root_digest, None, 0)


def verified_layer(raw: bytes, diff_id: str) -> bytes:

    if _sha256(raw) == diff_id:
        return raw
    if not raw.startswith(b"\x1f\x8b"):
        raise ValueError("base layer digest mismatch")

    limit = min(MAX_MEMBER_BYTES, 512 * 1024 * 1024)
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            uncompressed = stream.read(limit + 1)
    except (EOFError, OSError, zlib.error) as exc:
        raise ValueError("invalid gzip layer") from exc

    if len(uncompressed) > limit:
        raise ValueError("decompressed layer exceeds size limit")
    if _sha256(uncompressed) != diff_id:
        raise ValueError("base layer digest mismatch")
    return uncompressed

def prepare(base: str, root: Path) -> None:
    _immutable_ref(base)
    registry_config_digest = verified_registry_config(base)
    subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", base], check=True
    )
    inspected = _json(subprocess.check_output(
        ["docker", "image", "inspect", base], text=True
    ))
    if (
        not isinstance(inspected, list)
        or len(inspected) != 1
        or not isinstance(inspected[0], dict)
    ):
        raise ValueError("ambiguous base inspection")
    expected = inspected[0]
    if expected.get("Architecture") != "amd64" or expected.get("Os") != "linux":
        raise ValueError("the release base must be linux/amd64")
    rootfs = expected.get("RootFS")
    if not isinstance(rootfs, dict) or rootfs.get("Type") != "layers":
        raise ValueError("invalid inspected root filesystem")
    diff_ids = rootfs.get("Layers")
    if not isinstance(diff_ids, list):
        raise TypeError("invalid inspected root filesystem layers")
    for digest in diff_ids:
        _digest(digest)

    blobs = root / "blobs" / "sha256"
    blobs.mkdir(parents=True, exist_ok=True)

    def blob(raw: bytes, media: str) -> dict:
        digest = hashlib.sha256(raw).hexdigest()
        (blobs / digest).write_bytes(raw)
        return {
            "mediaType": media,
            "digest": "sha256:" + digest,
            "size": len(raw),
        }

    with tempfile.TemporaryDirectory(prefix="base-save-", dir=root.parent) as temporary:
        archive_path = Path(temporary) / "image.tar"
        subprocess.run(
            ["docker", "save", "-o", str(archive_path), base], check=True
        )
        with tarfile.open(archive_path) as archive:
            members = {}
            duplicates = set()
            for member in archive:
                if member.name in members:
                    duplicates.add(member.name)
                else:
                    members[member.name] = member

            def read(name: str) -> bytes:
                if not isinstance(name, str) or not name:
                    raise ValueError("invalid base archive member path")
                if name in duplicates:
                    raise ValueError("duplicate base archive member path")
                member = members.get(name)
                if member is None:
                    raise ValueError("missing base archive member")
                if not member.isfile():
                    raise ValueError("base archive member must be regular")
                if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                    raise ValueError("base archive member exceeds size limit")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("missing base archive member data")
                with stream:
                    raw = stream.read(member.size + 1)
                if len(raw) != member.size:
                    raise ValueError("base archive member size mismatch")
                return raw

            images = _json(read("manifest.json"))
            if (
                not isinstance(images, list)
                or len(images) != 1
                or not isinstance(images[0], dict)
            ):
                raise ValueError("ambiguous base archive")
            image = images[0]
            raw = read(image.get("Config"))
            actual_config_digest = _sha256(raw)
            if actual_config_digest != registry_config_digest:
                raise ValueError("base config digest mismatch")
            config_document = _json(raw)
            if not isinstance(config_document, dict):
                raise TypeError("invalid base config")
            if (
                config_document.get("architecture") != "amd64"
                or config_document.get("os") != "linux"
            ):
                raise ValueError("base config must be linux/amd64")
            config_rootfs = config_document.get("rootfs")
            if (
                not isinstance(config_rootfs, dict)
                or config_rootfs.get("type") != "layers"
                or config_rootfs.get("diff_ids") != diff_ids
            ):
                raise ValueError("base config root filesystem mismatch")
            config = blob(raw, OCI_CONFIG)
            layer_paths = image.get("Layers")
            if not isinstance(layer_paths, list) or len(layer_paths) != len(diff_ids):
                raise ValueError("base archive layer count mismatch")
            layers = []
            for path, digest in zip(layer_paths, diff_ids, strict=True):
                raw = verified_layer(read(path), digest)
                layers.append(blob(raw, "application/vnd.oci.image.layer.v1.tar"))

    manifest = blob(
        json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": OCI_MANIFEST,
                "config": config,
                "layers": layers,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
        OCI_MANIFEST,
    )
    (root / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
    (root / "index.json").write_text(json.dumps({
        "schemaVersion": 2,
        "manifests": [{
            **manifest,
            "annotations": {
                "org.opencontainers.image.ref.name": "verified-base"
            },
            "platform": {"os": "linux", "architecture": "amd64"},
        }],
    }))
    print(json.dumps({
        "approved_base": base,
        "verified_config": actual_config_digest,
        "layers": len(layers),
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.base, args.output)
