"""Exercise the release shell entry point without ripgrep or a real Docker service."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/release/build-images.sh'
BUILDKIT = 'moby/buildkit@sha256:6eceb8971ce4fceb3daca562832642706238b7eea72941fcf9896c93c3c4a53e'


@pytest.mark.parametrize('driver', ['docker-container', 'docker', 'kubernetes'])
def test_release_driver_guard_without_ripgrep(tmp_path, driver):
    binaries = tmp_path/'bin'
    binaries.mkdir()
    # Supply only the actual portable text utility and controlled API substitutes.
    (binaries/'grep').symlink_to(shutil.which('grep'))
    commands = {
        'git': '''case "$1" in
            status) exit 0;;
            show) echo 1234567890;;
            rev-parse) echo fixture-revision;;
            *) exit 99;;
        esac''',
        'python': 'exit 0',
        'docker': '''if [[ "$1 $2" == "buildx inspect" ]]; then
            printf 'Name: fixture\nDriver: %s\nNodes: fixture\n' "$FIXTURE_DRIVER"
        elif [[ "$1" == "inspect" ]]; then
            echo "$FIXTURE_BUILDKIT"
        elif [[ "$1 $2" == "buildx build" ]]; then
            printf '%s\n' "$*" >> "$FIXTURE_BUILDS"
        else
            exit 99
        fi''',
    }
    for name, body in commands.items():
        executable = binaries/name
        executable.write_text('#!/bin/bash\nset -euo pipefail\n'+body+'\n')
        executable.chmod(0o755)
    builds = tmp_path/'builds'
    result = subprocess.run(['/bin/bash', str(SCRIPT)], cwd=tmp_path,
        env={**os.environ, 'PATH': str(binaries), 'PHYSIMESH_PYTHON_BASE': 'python@sha256:'+'a'*64,
             'PHYSIMESH_RELEASE_BUILDER': 'fixture-builder', 'FIXTURE_DRIVER': driver,
             'FIXTURE_BUILDKIT': BUILDKIT, 'FIXTURE_BUILDS': str(builds)},
        capture_output=True, text=True, check=False, timeout=10)
    if driver == 'docker-container':
        assert result.returncode == 0, result.stderr
        calls = builds.read_text().splitlines()
        assert len(calls) == 2
        assert '--target application' in calls[0] and '--target worker' in calls[1]
        assert all('--network none' in call and 'rewrite-timestamp=true' in call for call in calls)
    else:
        assert result.returncode != 0
        assert 'requires the dedicated docker-container exporter' in result.stderr
        assert not builds.exists()
