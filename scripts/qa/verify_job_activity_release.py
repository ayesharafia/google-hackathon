"""Verify scoped source protection, syntax, local docs/evidence and wheel assets."""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--baseline", required=True)
args = parser.parse_args()
protected = subprocess.check_output(
    ["git", "diff", "--name-only", args.baseline, "--", "src", "tests/platform",
     "tests/projects", "tests/drone", "reference_impl", "pyproject.toml", "setup.py",
     "requirements-runtime.lock", "requirements-platform.lock", "requirements-test.lock"],
    cwd=root, text=True,
).splitlines()
assert not protected, protected
scripts = ["web/js/job-activity.js", "web/js/workbench.js",
           "tests/web/test_job_activity.mjs", "scripts/qa/job_activity_browser.mjs"]
for script in scripts:
    subprocess.run(["node", "--check", script], cwd=root, check=True, capture_output=True)
for script in ["scripts/qa/job_activity_fixture.py", "scripts/qa/verify_job_activity_release.py"]:
    ast.parse((root / script).read_text())
docs = ["docs/technical/job-activity.md", "docs/qa/job-activity-2026-10-26.md",
        "docs/qa/job-activity-design-law-2026-10-26.md"]
links = 0
for name in docs:
    path = root / name
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
        if "://" not in target and not target.startswith("#"):
            assert (path.parent / target.split("#")[0]).is_file(), (name, target)
            links += 1
assert len(re.findall(r"^\| \d+\. ", (root / docs[-1]).read_text(), re.MULTILINE)) == 147
work = Path(tempfile.mkdtemp(prefix="job-activity-wheel-", dir=root / ".backend"))
result = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(work)], cwd=root,
                        text=True, capture_output=True, timeout=90, check=False)
assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
wheel = next(work.glob("*.whl"))
assets = ["js/job-activity.js", "js/workbench.js", "css/workbench.css", "workbench.html"]
with zipfile.ZipFile(wheel) as archive:
    build = json.loads(archive.read("physimesh/_build.json"))
    for asset in assets:
        name = "resources/web/" + asset
        raw = (root / "web" / asset).read_bytes()
        assert archive.read("physimesh/" + name) == raw, name
        assert build["resources"][name] == hashlib.sha256(raw).hexdigest(), name
evidence = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "docs/qa/assets/job-activity").rglob("*")) if path.is_file()}
assert len(evidence) == 7
subprocess.run(["git", "diff", "--check"], cwd=root, check=True, capture_output=True)
print(json.dumps({"protected_paths_changed": protected, "syntax_checked": scripts,
                  "python_syntax_files": 2, "valid_local_links": links, "law_entries": 147,
                  "wheel_assets": assets, "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                  "evidence_sha256": evidence, "limits": "Local software/release evidence, no deployment."}, indent=2))
