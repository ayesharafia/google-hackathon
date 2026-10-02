from pathlib import Path

from physimesh.core.container import docker_run_args
from physimesh.core.jobs import Budgets


def test_hardening_flags_present():
    args = docker_run_args("img@sha256:" + "a" * 64, Path("/data/case1"), ["simpleFoam"],
                           Budgets(4, 8, 20, 7200, 512))
    for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL", "--pids-limit", "512",
                 "--cpus", "4", "--memory", "8g"):
        assert flag in args
    assert "img@sha256:" + "a" * 64 in args           # image referenced by digest, never by tag


def test_tag_reference_refused():
    import pytest
    with pytest.raises(ValueError):
        docker_run_args("opencfd/openfoam:latest", Path("/c"), ["x"], Budgets(1, 1, 1, 1, 64))


def test_malformed_digest_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        docker_run_args("image@sha256:bad", Path("/case"), ["x"], Budgets(1, 1, 1, 1, 64))
