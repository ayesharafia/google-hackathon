"""Bounded local checks through the existing task ledger, not a second engine.

Usage: python scripts/qa/atmosphere_loop.py --task ATMOS-001
The task must already be scoped and started by the existing workflow. This
runner executes no AI, repair, remote writes, approvals or completion command.
It retains a failed check and stops; a reviewed code repair is a separate step.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ["tests/drone/test_standard_atmosphere.py", "tests/drone/test_atmosphere_api.py",
         "tests/drone/test_atmosphere_auth_contract.py", "tests/drone/test_atmosphere_application.py"]
SOURCES = ["src/physimesh/drone/standard_atmosphere.py", "src/physimesh/api/atmosphere.py",
           "src/physimesh/api/app.py", "scripts/qa/agent_fixture.py", "scripts/qa/atmosphere_loop.py", *TESTS]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    workflow = ROOT / ".physicore/tools/workflow.py"
    environment = dict(os.environ)
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    environment["PYTHONPATH"] = str(ROOT / "src")
    for command in ([sys.executable, "-m", "ruff", "check", *SOURCES],
                    [sys.executable, "-m", "pytest", "-q", *TESTS]):
        # workflow's allowlist requires a command name; reuse this interpreter
        # via PATH in the environment in which the existing workflow was started.
        command[0] = "python"
        completed = subprocess.run(
            [sys.executable, str(workflow), "check", "--timeout", "120", args.task, "--", *command],
            cwd=ROOT, env=environment, timeout=150, check=False,
        )
        if completed.returncode:
            return completed.returncode
    print("Checks recorded. Independent review and full application gates remain separate; task not completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
