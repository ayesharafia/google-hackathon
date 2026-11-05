import copy
import hashlib
import json
import os
import stat
from types import SimpleNamespace

import pytest

from scripts.qa import codex_review_bundle as b


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


@pytest.fixture
def inputs():
    digest = sha(b"old\n")
    snapshot = {
        "schema_version": 1,
        "task_id": "T",
        "started_at": "arbitrary",
        "base_head": "a" * 40,
        "task_instruction": "Replace old with new.",
        "sources": {"src/a.py": {"text": "old\n", "sha256": digest}},
        "editable_paths": ["src/a.py"],
    }
    proposal = {
        "schema_version": 1,
        "task_id": "T",
        "started_at": "arbitrary",
        "base_head": "a" * 40,
        "input_hashes": {"src/a.py": digest},
        "changes": [{
            "path": "src/a.py",
            "before_sha256": digest,
            "after_text": "new\n",
        }],
        "facts": [],
    }
    return snapshot, proposal


@pytest.fixture
def artifacts(inputs):
    return b.build_bundle(*inputs)


def os_proxy(monkeypatch, **overrides):
    proxy = SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})
    for name, value in overrides.items():
        setattr(proxy, name, value)
    monkeypatch.setattr(b, "os", proxy)


def test_deterministic_canonical_inputs(inputs, artifacts):
    assert b.build_bundle(*copy.deepcopy(inputs)) == artifacts
    assert artifacts["request-snapshot.json"] == canonical(inputs[0])
    assert artifacts["proposal.json"] == canonical(inputs[1])
    for name, data in artifacts.items():
        if name.endswith(".json"):
            assert data == canonical(json.loads(data))


def test_manifest_hashes_sizes_and_names(artifacts):
    manifest = json.loads(artifacts["bundle.json"])
    assert set(artifacts) == b._FIXED_NAMES | {"replacements/000.txt"}
    assert manifest["artifacts"] == {
        name: {"sha256": sha(data), "bytes": len(data)}
        for name, data in artifacts.items() if name != "bundle.json"
    }


def test_replacement_and_change_metadata(artifacts, inputs):
    assert artifacts["replacements/000.txt"] == b"new\n"
    assert json.loads(artifacts["changes.json"]) == {
        "schema_version": 1,
        "changes": [{
            "path": "src/a.py",
            "before_sha256": inputs[1]["changes"][0]["before_sha256"],
            "after_sha256": sha(b"new\n"),
            "bytes": 4,
            "artifact": "replacements/000.txt",
        }],
    }


def test_unverified_metadata_and_inert_facts(artifacts):
    for name in ("bundle.json", "result.json"):
        value = json.loads(artifacts[name])
        assert value["status"] == "review_required"
        for key in ("provider_invoked", "head_verified", "authority_verified",
                    "approval_verified", "current_state_verified",
                    "snapshot_provenance_verified", "facts_verified",
                    "completion_allowed", "secret_redaction_claimed"):
            assert value[key] is False
        assert value["facts_inert"] is True
        assert value["diff_representational_only"] is True
        assert value["source_text_included"] is True
    assert json.loads(artifacts["facts.json"]) == {
        "schema_version": 1, "inert": True, "verified": False, "facts": [],
    }


def test_build_does_not_mutate_inputs_or_sources(inputs, tmp_path, monkeypatch):
    source = tmp_path / "src/a.py"
    source.parent.mkdir()
    source.write_bytes(b"live source\n")
    monkeypatch.chdir(tmp_path)
    original = copy.deepcopy(inputs)
    b.build_bundle(*inputs)
    assert inputs == original
    assert source.read_bytes() == b"live source\n"


def test_existing_validator_reused_on_detached_copies(inputs, monkeypatch):
    real = b.validate_proposal
    calls = []

    def spy(snapshot, proposal):
        calls.append((snapshot, proposal))
        assert snapshot is not inputs[0] and proposal is not inputs[1]
        return real(snapshot, proposal)

    monkeypatch.setattr(b, "validate_proposal", spy)
    b.build_bundle(*inputs)
    assert len(calls) == 1
    assert calls[0] == inputs


@pytest.mark.parametrize("key,value", [
    ("schema_version", 2), ("task_id", "other"), ("base_head", "b" * 40),
    ("input_hashes", {}), ("input_hashes", {"src/a.py": "0" * 64}),
])
def test_invalid_proposal_identity_and_hashes(inputs, key, value):
    inputs[1][key] = value
    with pytest.raises(b.BundleInputError):
        b.build_bundle(*inputs)


@pytest.mark.parametrize("patch", [
    {"path": "../a.py"}, {"path": "/src/a.py"}, {"path": "src/missing.py"},
    {"before_sha256": "0" * 64}, {"after_text": 42},
])
def test_invalid_changes(inputs, patch):
    inputs[1]["changes"][0].update(patch)
    with pytest.raises(b.BundleInputError):
        b.build_bundle(*inputs)


def test_invalid_snapshot_hash_and_editable_paths(inputs):
    for field, value in (("sha256", "0" * 64), ("text", "different")):
        snapshot = copy.deepcopy(inputs[0])
        snapshot["sources"]["src/a.py"][field] = value
        with pytest.raises(b.BundleInputError):
            b.build_bundle(snapshot, inputs[1])
    inputs[0]["editable_paths"] = []
    with pytest.raises(b.BundleInputError):
        b.build_bundle(*inputs)


@pytest.mark.parametrize("value", [set(), (1,), {1: "x"}, float("nan"),
                                  float("inf"), float("-inf"), "\ud800"])
def test_build_rejects_non_json_values(inputs, value):
    inputs[0]["extra"] = value
    with pytest.raises(b.BundleInputError):
        b.build_bundle(*inputs)


def test_build_size_and_depth_limits(inputs, monkeypatch):
    monkeypatch.setattr(b, "_INPUT_LIMIT", 10)
    with pytest.raises(b.BundleInputError):
        b.build_bundle(*inputs)
    nested = None
    for _ in range(66):
        nested = [nested]
    with pytest.raises(b.BundleInputError):
        b._canonical(nested)


@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
    b'{"x":-Infinity}', b'"\\ud800"', b'"\xff"',
])
def test_strict_load_rejects_bad_json(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    with pytest.raises(b.BundleInputError):
        b.strict_load(path, 1024)


def test_strict_load_valid_and_oversize(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b'{"x":1}\n')
    assert b.strict_load(path, 8) == {"x": 1}
    with pytest.raises(b.BundleInputError):
        b.strict_load(path, 7)


def test_strict_load_read_growth(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_bytes(b"0")
    chunks = iter([b"12345", b""])
    os_proxy(monkeypatch, read=lambda *_: next(chunks))
    with pytest.raises(b.BundleInputError):
        b.strict_load(path, 4)


@pytest.mark.parametrize("kind", ["file", "intermediate", "directory", "fifo"])
def test_strict_load_rejects_special_paths(tmp_path, kind):
    target = tmp_path / "target"
    target.write_bytes(b"{}")
    path = tmp_path / "input"
    if kind == "file":
        path.symlink_to(target)
    elif kind == "intermediate":
        path.symlink_to(tmp_path, target_is_directory=True)
        path = path / "target"
    elif kind == "directory":
        path.mkdir()
    else:
        os.mkfifo(path)
    with pytest.raises(b.BundleInputError):
        b.strict_load(path, 1024)


@pytest.mark.parametrize("limit", [True, False, 0, -1, 1.5, b._INPUT_LIMIT + 1])
def test_strict_load_invalid_caps(tmp_path, limit):
    with pytest.raises(b.BundleInputError):
        b.strict_load(tmp_path / "absent", limit)


def test_lexical_dotdot_rejected(tmp_path):
    with pytest.raises(b.BundleInputError):
        b.strict_load(str(tmp_path) + "/../input.json", 1024)


def test_publication_names_bytes_and_permissions(tmp_path, artifacts):
    output = tmp_path / "bundle"
    b.write_bundle(output, artifacts)
    files = {str(p.relative_to(output)): p.read_bytes()
             for p in output.rglob("*") if p.is_file()}
    assert files == artifacts
    for directory in (output, output / "replacements"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600
               for p in output.rglob("*") if p.is_file())


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "parent"])
def test_publication_no_overwrite_or_symlink_parent(tmp_path, artifacts, kind):
    output = tmp_path / "bundle"
    if kind == "file":
        output.write_bytes(b"sentinel")
    elif kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(tmp_path, target_is_directory=True)
        if kind == "parent":
            output = output / "nested"
    with pytest.raises(b.BundlePublicationError):
        b.write_bundle(output, artifacts)
    assert not (tmp_path / "nested").exists()
    if kind == "file":
        assert output.read_bytes() == b"sentinel"


@pytest.mark.parametrize("tamper", ["manifest", "name", "index", "bytes"])
def test_invalid_artifacts_rejected_before_creation(tmp_path, artifacts, tamper):
    bad = dict(artifacts)
    if tamper == "manifest":
        bad["bundle.json"] = b"{}\n"
    elif tamper == "name":
        bad["../escape"] = b"x"
    elif tamper == "index":
        bad["replacements/002.txt"] = bad.pop("replacements/000.txt")
    else:
        bad["proposal.diff"] += b"tampered"
    output = tmp_path / "bundle"
    with pytest.raises(b.BundlePublicationError):
        b.write_bundle(output, bad)
    assert not output.exists()


@pytest.mark.parametrize("operation", ["write", "fsync", "link"])
def test_publication_failures_leave_no_marker(tmp_path, artifacts, monkeypatch, operation):
    real_write = os.write

    def fail(*args, **kwargs):
        raise OSError("private failure")

    writes = 0

    def partial(fd, data):
        nonlocal writes
        writes += 1
        return real_write(fd, data[:1]) if writes == 1 else fail()

    os_proxy(monkeypatch, **{operation: partial if operation == "write" else fail})
    output = tmp_path / "bundle"
    with pytest.raises(b.BundlePublicationError, match="^publication_error$"):
        b.write_bundle(output, artifacts)
    assert output.is_dir()
    assert not (output / "bundle.json").exists()


def test_short_writes_handled_and_fd_closed(tmp_path, monkeypatch):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_write, real_close = os.write, os.close
    closed = []
    os_proxy(monkeypatch, write=lambda f, data: real_write(f, data[:2]),
             close=lambda f: (closed.append(f), real_close(f))[1])
    try:
        b._write_file(fd, "small", b"abcdef")
        assert (tmp_path / "small").read_bytes() == b"abcdef"
        assert len(closed) == 1
        with pytest.raises(OSError):
            os.fstat(closed[0])
    finally:
        real_close(fd)


def test_failed_write_closes_fd(tmp_path, monkeypatch):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    closed, real_close = [], os.close
    os_proxy(monkeypatch, write=lambda *_: 0,
             close=lambda f: (closed.append(f), real_close(f))[1])
    try:
        with pytest.raises(OSError):
            b._write_file(fd, "failed", b"x")
        assert len(closed) == 1
        with pytest.raises(OSError):
            os.fstat(closed[0])
    finally:
        real_close(fd)


def test_manifest_published_last(tmp_path, artifacts, monkeypatch):
    events, real_write, real_link = [], b._write_file, os.link

    def write(fd, name, data):
        events.append(name)
        return real_write(fd, name, data)

    def link(*args, **kwargs):
        assert events[-1] == ".bundle.json.tmp"
        events.append("bundle.json")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(b, "_write_file", write)
    os_proxy(monkeypatch, link=link)
    b.write_bundle(tmp_path / "bundle", artifacts)
    assert events[-1] == "bundle.json"


@pytest.mark.parametrize("args", [[], ["--help"], ["--snapshot=SECRET"],
                                  ["--unknown", "SECRET"]])
def test_cli_invalid_arguments_sanitized(args, capsys):
    assert b.main(args) == 2
    assert capsys.readouterr().out == '{"error":"invalid_input","status":"invalid_input"}\n'


def test_cli_success_matches_files_without_source_writes(inputs, artifacts, tmp_path, capsys):
    snapshot, proposal, output = (tmp_path / n for n in ("s.json", "p.json", "bundle"))
    snapshot.write_bytes(canonical(inputs[0]))
    proposal.write_bytes(canonical(inputs[1]))
    before = snapshot.read_bytes(), proposal.read_bytes()
    assert b.main(["--snapshot", str(snapshot), "--proposal", str(proposal),
                   "--output-dir", str(output)]) == 0
    assert capsys.readouterr().out == '{"status":"finalized"}\n'
    assert all((output / name).read_bytes() == data for name, data in artifacts.items())
    assert (snapshot.read_bytes(), proposal.read_bytes()) == before


@pytest.mark.parametrize("stage,code,status", [
    ("strict_load", 2, "invalid_input"), ("write_bundle", 3, "publication_error"),
])
def test_cli_expected_failure_sanitization(monkeypatch, capsys, stage, code, status):
    def fail(*args):
        raise ValueError("SECRET raw source text")
    monkeypatch.setattr(b, "strict_load", lambda *_: {})
    monkeypatch.setattr(b, "build_bundle", lambda *_: {})
    monkeypatch.setattr(b, stage, fail)
    assert b.main(["--snapshot", "/s", "--proposal", "/p", "--output-dir", "/o"]) == code
    assert json.loads(capsys.readouterr().out) == {"status": status, "error": status}


def test_missing_terminal_lf_diff_is_representational(inputs):
    inputs[0]["sources"]["src/a.py"] = {"text": "old", "sha256": sha(b"old")}
    inputs[1]["input_hashes"]["src/a.py"] = sha(b"old")
    inputs[1]["changes"][0].update(before_sha256=sha(b"old"), after_text="new")
    original = copy.deepcopy(inputs)
    artifacts = b.build_bundle(*inputs)
    assert b"-old\n\\ No newline at end of file\n+new\n" in artifacts["proposal.diff"]
    assert artifacts["replacements/000.txt"] == b"new"
    assert inputs == original


@pytest.mark.parametrize('stage,code,status', [
    ('strict_load', 2, 'invalid_input'), ('write_bundle', 3, 'publication_error'),
])
def test_cli_unexpected_errors_sanitized(monkeypatch, capsys, stage, code, status):
    def fail(*args):
        raise RuntimeError('source-bearing internal error')
    monkeypatch.setattr(b, 'strict_load', lambda *_: {})
    monkeypatch.setattr(b, 'build_bundle', lambda *_: {})
    monkeypatch.setattr(b, stage, fail)
    assert b.main(['--snapshot', '/s', '--proposal', '/p', '--output-dir', '/o']) == code
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'status': status, 'error': status}
    assert captured.err == ''


def test_publication_after_link_failure_removes_marker(tmp_path, artifacts, monkeypatch):
    real_unlink = os.unlink
    def fail_temporary(name, **kwargs):
        if name == b._TEMP_MANIFEST:
            raise OSError('temporary unlink failed')
        return real_unlink(name, **kwargs)
    os_proxy(monkeypatch, unlink=fail_temporary)
    output = tmp_path / 'bundle'
    with pytest.raises(b.BundlePublicationError):
        b.write_bundle(output, artifacts)
    assert not (output / 'bundle.json').exists()
