"""Task 1.4: real v2606 tutorial meshing under the hardened runner [M§26]."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from physimesh.core.container import docker_run_args
from physimesh.core.jobs import Budgets

# Vendor image inspected locally, 2026-10-02; see docs/audit/backend_pin.md.
IMAGE = "opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb"


@pytest.mark.backend
def test_v2606_tutorial_mesh_in_hardened_container(tmp_path):
    tutorials = os.environ.get("PHYSIMESH_OPENFOAM_TUTORIALS")
    if not tutorials:
        pytest.skip("Set PHYSIMESH_OPENFOAM_TUTORIALS to the hash-verified v2606 source tutorials")
    source = Path(tutorials) / "incompressible/simpleFoam/squareBend"
    assert source.is_dir(), f"Missing vendor tutorial: {source}"
    case = tmp_path / "case"
    shutil.copytree(source, case)
    # Resource limits are fixture choices, not vehicle inputs [ASSUMPTION].
    budgets = Budgets(2, 4, 2, 120, 512)
    # Vendor entrypoint resets cwd, so explicitly enter the writable case mount.
    cmd = ["bash", "-lc", "set -e; cd /case; blockMesh; checkMesh"]
    result = subprocess.run(docker_run_args(IMAGE, case, cmd, budgets),
                            capture_output=True, text=True, timeout=budgets.wall_time_s, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "version=2606" in result.stdout
    assert "Mesh OK." in result.stdout
    assert (case / "constant/polyMesh/points").is_file()
