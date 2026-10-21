"""Bind an offline OCI context to Docker's digest-verified immutable base."""
import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path


def prepare(base: str, root: Path) -> None:
    if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", base):
        raise ValueError("an immutable base digest is required")
    subprocess.run(["docker", "pull", "--platform", "linux/amd64", base], check=True)
    expected = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", base], text=True))[0]
    if expected["Architecture"] != "amd64" or expected["Os"] != "linux":
        raise ValueError("the release base must be linux/amd64")
    blobs = root / "blobs" / "sha256"
    blobs.mkdir(parents=True, exist_ok=True)

    def blob(raw: bytes, media: str) -> dict:
        digest = hashlib.sha256(raw).hexdigest()
        (blobs / digest).write_bytes(raw)
        return {"mediaType": media, "digest": "sha256:" + digest, "size": len(raw)}

    with tempfile.TemporaryDirectory(prefix="base-save-", dir=root.parent) as temporary:
        archive_path = Path(temporary) / "image.tar"
        subprocess.run(["docker", "save", "-o", str(archive_path), base], check=True)
        with tarfile.open(archive_path) as archive:
            def read(name: str) -> bytes:
                member = archive.extractfile(name)
                if member is None:
                    raise ValueError("missing base archive member")
                return member.read()

            images = json.loads(read("manifest.json"))
            if len(images) != 1:
                raise ValueError("ambiguous base archive")
            image = images[0]
            raw = read(image["Config"])
            if "sha256:" + hashlib.sha256(raw).hexdigest() != expected["Id"]:
                raise ValueError("base config digest mismatch")
            config = blob(raw, "application/vnd.oci.image.config.v1+json")
            layers = []
            for path, digest in zip(image["Layers"], expected["RootFS"]["Layers"], strict=True):
                raw = read(path)
                if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
                    raise ValueError("base layer digest mismatch")
                layers.append(blob(raw, "application/vnd.oci.image.layer.v1.tar"))
    manifest = blob(json.dumps({"schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json", "config": config,
        "layers": layers}, sort_keys=True, separators=(",", ":")).encode(),
        "application/vnd.oci.image.manifest.v1+json")
    (root / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
    (root / "index.json").write_text(json.dumps({"schemaVersion": 2, "manifests": [{
        **manifest, "annotations": {"org.opencontainers.image.ref.name": "verified-base"},
        "platform": {"os": "linux", "architecture": "amd64"}}]}))
    print(json.dumps({"approved_base": base, "verified_config": expected["Id"],
                      "layers": len(layers)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.base, args.output)
