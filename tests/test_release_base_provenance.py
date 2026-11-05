import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

OCI_INDEX = "application/vnd.oci.image.index.v1+json"
DOCKER_INDEX = "application/vnd.docker.distribution.manifest.list.v2+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
DOCKER_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
OCI_CONFIG = "application/vnd.oci.image.config.v1+json"
DOCKER_CONFIG = "application/vnd.docker.container.image.v1+json"
OCI_LAYER = "application/vnd.oci.image.layer.v1.tar"
DOCKER_LAYER = "application/vnd.docker.image.rootfs.diff.tar.gzip"


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def descriptor(raw, media, **extra):
    return {"mediaType": media, "digest": digest(raw), "size": len(raw), **extra}


def layer_tar():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo("hello.txt")
        payload = b"verified layer\n"
        info.size = len(payload)
        info.mtime = 0
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


@pytest.fixture
def module():
    relative = Path("scripts/release/prepare-base.py")
    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    path = next(
        (root / relative for root in candidates if (root / relative).is_file()),
        None,
    )
    assert path is not None, f"Cannot locate {relative} from the repository root"
    spec = importlib.util.spec_from_file_location("prepare_base_under_test", path)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class BaseCase:
    def __init__(self, module, monkeypatch, tmp_path, docker=False):
        self.module = module
        self.tmp_path = tmp_path
        self.output = tmp_path / "output"
        self.archive = tmp_path / "docker-save.tar"
        self.repository = "registry.example.test:5000/team/base"
        self.layer = layer_tar()
        self.config = {
            "architecture": "amd64",
            "os": "linux",
            "rootfs": {"type": "layers", "diff_ids": [digest(self.layer)]},
        }
        self.config_raw = encode(self.config) + b"\n"
        self.config_name = "config.json"
        self.layer_name = "layer/layer.tar"
        self.manifest_media = DOCKER_MANIFEST if docker else OCI_MANIFEST
        self.index_media = DOCKER_INDEX if docker else OCI_INDEX
        self.config_media = DOCKER_CONFIG if docker else OCI_CONFIG
        self.layer_media = DOCKER_LAYER if docker else OCI_LAYER
        self.manifest = {
            "schemaVersion": 2,
            "mediaType": self.manifest_media,
            "config": descriptor(self.config_raw, self.config_media),
            "layers": [descriptor(b"registry-compressed-layer", self.layer_media)],
        }
        self.inspection = {
            "Id": digest(self.config_raw),
            "Architecture": "amd64",
            "Os": "linux",
            "RootFS": {"Type": "layers", "Layers": [digest(self.layer)]},
        }
        self.saved_manifest = [{
            "Config": self.config_name,
            "RepoTags": [],
            "Layers": [self.layer_name],
        }]
        self.registry = {}
        self.calls = []
        self.failure = None
        self.rebuild_registry()
        self.write_archive()
        monkeypatch.setattr(module.subprocess, "check_output", self.check_output)
        monkeypatch.setattr(module.subprocess, "run", self.run)

    def rebuild_registry(self, depth=1, index_entries=None, manifest_raw=None):
        self.registry = {}
        raw = encode(self.manifest) if manifest_raw is None else manifest_raw
        self.manifest_raw = raw
        self.manifest_digest = digest(raw)
        self.registry[digest(raw)] = raw
        media = self.manifest_media
        for level in range(depth):
            entry = descriptor(
                raw,
                media,
                platform={"os": "linux", "architecture": "amd64"},
            )
            entries = (
                copy.deepcopy(index_entries)
                if level == 0 and index_entries is not None
                else [entry]
            )
            raw = encode({
                "schemaVersion": 2,
                "mediaType": self.index_media,
                "manifests": entries,
            })
            media = self.index_media
            self.registry[digest(raw)] = raw
        self.root_raw = raw
        self.base = self.repository + "@" + digest(raw)

    def write_archive(self, entries=None):
        if entries is None:
            entries = [
                ("manifest.json", encode(self.saved_manifest)),
                (self.config_name, self.config_raw),
                (self.layer_name, self.layer),
            ]
        with tarfile.open(self.archive, "w") as archive:
            for name, content in entries:
                if isinstance(content, tarfile.TarInfo):
                    archive.addfile(content)
                else:
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))

    def check_output(self, command, **kwargs):
        self.calls.append(("check_output", command, kwargs))
        if self.failure == "registry":
            raise subprocess.CalledProcessError(17, command)
        if command[:5] == ["docker", "buildx", "imagetools", "inspect", "--raw"]:
            assert kwargs == {}
            assert len(command) == 6
            repository, requested_digest = command[-1].split("@")
            assert repository == self.repository
            assert requested_digest in self.registry
            return self.registry[requested_digest]
        assert command == ["docker", "image", "inspect", self.base]
        assert kwargs == {"text": True}
        if self.failure == "inspect":
            raise subprocess.CalledProcessError(17, command)
        return json.dumps([self.inspection])

    def run(self, command, **kwargs):
        self.calls.append(("run", command, kwargs))
        assert kwargs == {"check": True}
        if command == ["docker", "pull", "--platform", "linux/amd64", self.base]:
            if self.failure == "pull":
                raise subprocess.CalledProcessError(17, command)
        else:
            assert command[:3] == ["docker", "save", "-o"]
            assert len(command) == 5 and command[-1] == self.base
            if self.failure == "save":
                raise subprocess.CalledProcessError(17, command)
            shutil.copyfile(self.archive, command[3])
        return subprocess.CompletedProcess(command, 0)

    def prepare(self):
        self.module.prepare(self.base, self.output)


@pytest.fixture
def case(module, monkeypatch, tmp_path):
    return BaseCase(module, monkeypatch, tmp_path)


def assert_descriptor_blob(root, entry):
    raw = (root / "blobs" / "sha256" / entry["digest"].split(":")[1]).read_bytes()
    assert digest(raw) == entry["digest"]
    assert len(raw) == entry["size"]
    return raw


@pytest.mark.parametrize("docker", [False, True], ids=["oci", "docker"])
@pytest.mark.parametrize("identity", ["config", "manifest"], ids=["classic", "containerd"])
def test_verified_base_accepts_both_image_id_forms(
    module, monkeypatch, tmp_path, capsys, docker, identity
):
    case = BaseCase(module, monkeypatch, tmp_path, docker=docker)
    case.inspection["Id"] = (
        digest(case.config_raw) if identity == "config" else case.manifest_digest
    )
    case.prepare()

    report = json.loads(capsys.readouterr().out)
    assert report == {
        "approved_base": case.base,
        "verified_config": digest(case.config_raw),
        "layers": 1,
    }
    assert json.loads((case.output / "oci-layout").read_bytes()) == {
        "imageLayoutVersion": "1.0.0"
    }
    index = json.loads((case.output / "index.json").read_bytes())
    assert index["schemaVersion"] == 2
    assert len(index["manifests"]) == 1
    entry = index["manifests"][0]
    assert entry["mediaType"] == OCI_MANIFEST
    assert entry["platform"] == {"os": "linux", "architecture": "amd64"}
    assert entry["annotations"] == {
        "org.opencontainers.image.ref.name": "verified-base"
    }
    manifest = json.loads(assert_descriptor_blob(case.output, entry))
    assert manifest["schemaVersion"] == 2
    assert manifest["mediaType"] == OCI_MANIFEST
    assert manifest["config"]["mediaType"] == OCI_CONFIG
    assert assert_descriptor_blob(case.output, manifest["config"]) == case.config_raw
    assert len(manifest["layers"]) == 1
    assert manifest["layers"][0]["mediaType"] == OCI_LAYER
    assert assert_descriptor_blob(case.output, manifest["layers"][0]) == case.layer

    expected_blobs = {
        item["digest"].split(":")[1]
        for item in [entry, manifest["config"], *manifest["layers"]]
    }
    assert {path.name for path in (case.output / "blobs" / "sha256").iterdir()} == expected_blobs
    registry_calls = [
        command[-1] for kind, command, _ in case.calls
        if command[:5] == ["docker", "buildx", "imagetools", "inspect", "--raw"]
    ]
    assert registry_calls == [
        case.base,
        case.repository + "@" + case.manifest_digest,
    ]
    assert [command[1] for kind, command, _ in case.calls if kind == "run"] == [
        "pull", "save"
    ]


@pytest.mark.parametrize("depth", [0, 2, 4])
def test_nested_index_depth_within_limit(case, depth):
    case.rebuild_registry(depth=depth)
    assert case.module.verified_registry_config(case.base) == digest(case.config_raw)
    assert len(case.calls) == depth + 1


def test_nested_index_depth_exceeded(case):
    case.rebuild_registry(depth=case.module.MAX_INDEX_DEPTH + 1)
    with pytest.raises(ValueError, match="depth limit"):
        case.prepare()
    assert all(kind != "run" for kind, _, _ in case.calls)


@pytest.mark.parametrize("fault", ["hash", "size", "media", "schema", "configdigest"])
def test_registry_chain_rejects_invalid_child(case, fault):
    if fault == "schema":
        case.manifest["schemaVersion"] = True
    elif fault == "configdigest":
        case.manifest["config"]["digest"] = "sha256:not-a-digest"
    case.rebuild_registry(depth=0)
    child = descriptor(
        case.manifest_raw,
        case.manifest_media,
        platform={"os": "linux", "architecture": "amd64"},
    )
    if fault == "size":
        child["size"] += 1
    elif fault == "media":
        child["mediaType"] = DOCKER_MANIFEST
    case.rebuild_registry(index_entries=[child])
    if fault == "hash":
        case.registry[case.manifest_digest] += b"\n"
    with pytest.raises((ValueError, TypeError)):
        case.prepare()
    assert all(kind != "run" for kind, _, _ in case.calls)


@pytest.mark.parametrize(
    "mutation",
    [
        {"schemaVersion": 1},
        {"schemaVersion": "2"},
        {"mediaType": "application/json"},
        {"layers": None},
        {"config": None},
    ],
)
def test_invalid_registry_manifest(case, mutation):
    case.manifest.update(mutation)
    case.rebuild_registry(depth=0)
    with pytest.raises((ValueError, TypeError)):
        case.prepare()


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("config", "size", True),
        ("config", "size", -1),
        ("config", "mediaType", DOCKER_CONFIG),
        ("layer", "digest", "sha256:" + "G" * 64),
        ("layer", "size", "12"),
        ("layer", "mediaType", "application/octet-stream"),
    ],
)
def test_invalid_registry_descriptors(case, target, field, value):
    entry = case.manifest["config"] if target == "config" else case.manifest["layers"][0]
    entry[field] = value
    case.rebuild_registry()
    with pytest.raises((ValueError, TypeError)):
        case.prepare()


@pytest.mark.parametrize("fault", ["architecture", "os", "variant", "ambiguous", "missing"])
def test_index_must_select_one_supported_platform(case, fault):
    entry = descriptor(
        case.manifest_raw,
        case.manifest_media,
        platform={"os": "linux", "architecture": "amd64"},
    )
    entries = [entry]
    if fault == "architecture":
        entry["platform"]["architecture"] = "arm64"
    elif fault == "os":
        entry["platform"]["os"] = "windows"
    elif fault == "variant":
        entry["platform"]["variant"] = "v2"
    elif fault == "ambiguous":
        entries.append(copy.deepcopy(entry))
    else:
        del entry["platform"]
    case.rebuild_registry(index_entries=entries)
    with pytest.raises((ValueError, TypeError)):
        case.prepare()
    assert all(kind != "run" for kind, _, _ in case.calls)


def test_index_ignores_other_architectures_and_accepts_v1(case):
    entry = descriptor(
        case.manifest_raw,
        case.manifest_media,
        platform={"os": "linux", "architecture": "amd64", "variant": "v1"},
    )
    other = copy.deepcopy(entry)
    other["platform"] = {"os": "linux", "architecture": "arm64", "variant": "v8"}
    case.rebuild_registry(index_entries=[other, entry])
    assert case.module.verified_registry_config(case.base) == digest(case.config_raw)


@pytest.mark.parametrize(
    "reference",
    [
        "ubuntu:latest",
        "ubuntu",
        "",
        "repo@" + "a" * 64,
        "repo@sha256:" + "A" * 64,
        "repo@sha256:" + "0" * 63,
        "repo:bad!tag@sha256:" + "0" * 64,
        "repo@@sha256:" + "0" * 64,
        "registry.test:0/repo@sha256:" + "0" * 64,
        "registry.test:65536/repo@sha256:" + "0" * 64,
        "registry.test//repo@sha256:" + "0" * 64,
        "../repo@sha256:" + "0" * 64,
        "https://registry.test/repo@sha256:" + "0" * 64,
    ],
)
def test_references_require_valid_immutable_digest(case, reference):
    with pytest.raises((ValueError, TypeError)):
        case.module.prepare(reference, case.output)
    assert case.calls == []


@pytest.mark.parametrize("field,value", [("Architecture", "arm64"), ("Os", "windows")])
def test_wrong_inspected_platform(case, field, value):
    case.inspection[field] = value
    with pytest.raises(ValueError, match="linux/amd64"):
        case.prepare()


@pytest.mark.parametrize("fault", ["digest", "architecture", "os", "rootfs", "diffids"])
def test_invalid_saved_config(case, fault):
    if fault == "digest":
        case.config_raw += b"\n"
    else:
        if fault == "architecture":
            case.config["architecture"] = "arm64"
        elif fault == "os":
            case.config["os"] = "windows"
        elif fault == "rootfs":
            case.config["rootfs"]["type"] = "other"
        else:
            case.config["rootfs"]["diff_ids"] = ["sha256:" + "f" * 64]
        case.config_raw = encode(case.config)
        case.manifest["config"] = descriptor(case.config_raw, case.config_media)
        case.rebuild_registry()
    case.write_archive()
    with pytest.raises(ValueError, match="config"):
        case.prepare()


@pytest.mark.parametrize("fault", ["hash", "count", "inspected_diffids"])
def test_invalid_layers(case, fault):
    if fault == "hash":
        case.layer += b"corruption"
    elif fault == "count":
        case.saved_manifest[0]["Layers"] = []
    else:
        case.inspection["RootFS"]["Layers"] = ["sha256:" + "e" * 64]
    case.write_archive()
    with pytest.raises(ValueError, match="layer|root filesystem"):
        case.prepare()


@pytest.mark.parametrize("target", ["registry", "archive_manifest", "config"])
def test_duplicate_json_keys_rejected(case, target):
    if target == "registry":
        raw = (
            b'{"schemaVersion":2,"schemaVersion":2,"mediaType":'
            + json.dumps(case.manifest_media).encode()
            + b"}"
        )
        case.rebuild_registry(depth=0, manifest_raw=raw)
    elif target == "archive_manifest":
        raw = (
            b'[{"Config":"config.json","Config":"config.json",'
            b'"Layers":["layer/layer.tar"]}]'
        )
        case.write_archive([
            ("manifest.json", raw),
            (case.config_name, case.config_raw),
            (case.layer_name, case.layer),
        ])
    else:
        case.config_raw = (
            b'{"architecture":"amd64","architecture":"amd64","os":"linux"}'
        )
        case.manifest["config"] = descriptor(case.config_raw, case.config_media)
        case.rebuild_registry()
        case.write_archive()
    with pytest.raises(ValueError, match="duplicate JSON key"):
        case.prepare()


@pytest.mark.parametrize("name", ["manifest.json", "config.json", "layer/layer.tar"])
def test_duplicate_archive_member_paths_rejected(case, name):
    entries = [
        ("manifest.json", encode(case.saved_manifest)),
        (case.config_name, case.config_raw),
        (case.layer_name, case.layer),
    ]
    entries.append(next(entry for entry in entries if entry[0] == name))
    case.write_archive(entries)
    with pytest.raises(ValueError, match="duplicate base archive member path"):
        case.prepare()


@pytest.mark.parametrize("name", ["manifest.json", "config.json", "layer/layer.tar"])
@pytest.mark.parametrize("fault", ["missing", "symlink", "oversize"])
def test_unsafe_or_missing_archive_members(case, monkeypatch, name, fault):
    entries = [
        ("manifest.json", encode(case.saved_manifest)),
        (case.config_name, case.config_raw),
        (case.layer_name, case.layer),
    ]
    if fault == "missing":
        entries = [entry for entry in entries if entry[0] != name]
    elif fault == "symlink":
        link = tarfile.TarInfo(name)
        link.type = tarfile.SYMTYPE
        link.linkname = "elsewhere"
        entries = [(key, link if key == name else value) for key, value in entries]
    else:
        original_open = case.module.tarfile.open

        def open_with_oversized_header(*args, **kwargs):
            archive = original_open(*args, **kwargs)
            original_next = archive.next

            def next_member():
                member = original_next()
                if member is not None and member.name == name:
                    member.size = case.module.MAX_MEMBER_BYTES + 1
                return member

            archive.next = next_member
            if archive.firstmember is not None and archive.firstmember.name == name:
                archive.firstmember.size = case.module.MAX_MEMBER_BYTES + 1
            return archive

        case.write_archive(entries)
        monkeypatch.setattr(case.module.tarfile, "open", open_with_oversized_header)
    if fault != "oversize":
        case.write_archive(entries)
    message = {
        "missing": "missing base archive member",
        "symlink": "must be regular",
        "oversize": "exceeds size limit",
    }[fault]
    with pytest.raises(ValueError, match=message):
        case.prepare()


def test_registry_raw_trailing_newline_is_authenticated(case):
    raw = encode(case.manifest) + b"\n"
    case.rebuild_registry(depth=0, manifest_raw=raw)
    assert case.module.verified_registry_config(case.base) == digest(case.config_raw)
    case.registry[digest(raw)] = raw.rstrip(b"\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        case.module.verified_registry_config(case.base)


def test_config_trailing_newline_is_not_normalized(case):
    assert case.config_raw.endswith(b"\n")
    case.config_raw = case.config_raw.rstrip(b"\n")
    case.write_archive()
    with pytest.raises(ValueError, match="base config digest mismatch"):
        case.prepare()


def test_registry_manifest_size_limit(case, monkeypatch):
    monkeypatch.setattr(case.module, "MAX_MEMBER_BYTES", len(case.root_raw) - 1)
    with pytest.raises(ValueError, match="registry manifest exceeds size limit"):
        case.prepare()


@pytest.mark.parametrize("stage", ["registry", "pull", "inspect", "save"])
def test_subprocess_failure_propagates(case, stage):
    case.failure = stage
    with pytest.raises(subprocess.CalledProcessError) as error:
        case.prepare()
    assert error.value.returncode == 17
    assert not (case.output / "index.json").exists()

def test_actual_ci_tag_plus_digest_reference(case):
    case.repository = "python:3.11.16-slim"
    case.rebuild_registry()
    case.prepare()


@pytest.mark.parametrize('docker', [False, True])
def test_gzip_saved_layers_preserve_verified_uncompressed_identity(module, monkeypatch, tmp_path, docker):
    import gzip
    case = BaseCase(module, monkeypatch, tmp_path, docker=docker)
    original = case.layer
    case.layer = gzip.compress(original, mtime=0)
    case.write_archive()
    case.prepare()
    assert (case.output / 'blobs/sha256' / digest(original).split(':')[1]).read_bytes() == original


@pytest.mark.parametrize('fault', ['crc', 'truncated', 'wrong-diffid', 'unknown-compression'])
def test_layer_decode_fails_closed(module, fault):
    import gzip
    raw = gzip.compress(b'approved uncompressed layer', mtime=0)
    expected = digest(b'approved uncompressed layer')
    if fault == 'crc':
        raw = raw[:-8] + bytes([raw[-8] ^ 1]) + raw[-7:]
    elif fault == 'truncated':
        raw = raw[:-4]
    elif fault == 'wrong-diffid':
        expected = digest(b'not the layer')
    else:
        raw = b'unsupported compression bytes'
    with pytest.raises(ValueError):
        module.verified_layer(raw, expected)


def test_decompressed_layer_limit(module, monkeypatch):
    import gzip
    monkeypatch.setattr(module, 'MAX_MEMBER_BYTES', 64)
    with pytest.raises(ValueError, match='size limit'):
        module.verified_layer(gzip.compress(b'a'*65), digest(b'a'*65))


def test_concatenated_gzip_members_bind_combined_bytes(module):
    import gzip
    raw = gzip.compress(b'first', mtime=0) + gzip.compress(b'second', mtime=0)
    assert module.verified_layer(raw, digest(b'firstsecond')) == b'firstsecond'
    with pytest.raises(ValueError):
        module.verified_layer(raw, digest(b'first'))
