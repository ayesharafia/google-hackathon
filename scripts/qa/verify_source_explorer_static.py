"""Scoped source protection, syntax, documentation and evidence checks."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--baseline", required=True)
args = parser.parse_args()
protected = subprocess.check_output(
    ["git", "diff", "--name-only", args.baseline, "--", "src", "tests/projects",
     "tests/platform", "tests/drone", "reference_impl", "pyproject.toml", "setup.py",
     "requirements-runtime.lock", "requirements-platform.lock", "requirements-test.lock"],
    cwd=root, text=True,
).splitlines()
assert not protected, protected
scripts = ["web/js/source-explorer.js", "web/js/source-library.js",
           "web/js/input-editors.js", "web/js/workbench.js",
           "tests/web/test_source_explorer.mjs", "scripts/qa/source_explorer_browser.mjs",
           "scripts/qa/source_explorer_viewer_browser.mjs"]
for script in scripts:
    subprocess.run(["node", "--check", script], cwd=root, check=True, capture_output=True)
docs = ["docs/technical/rotor-source-explorer.md",
        "docs/qa/rotor-source-explorer-2026-10-23.md",
        "docs/qa/rotor-source-explorer-design-law-2026-10-23.md"]
links = 0
for doc in docs:
    path = root / doc
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
        if "://" in target or target.startswith("#"):
            continue
        assert (path.parent / target.split("#")[0]).is_file(), (doc, target)
        links += 1
ledger = (root / docs[-1]).read_text()
assert len(re.findall(r"^\| \d+\. ", ledger, re.MULTILINE)) == 147
assert "@container source-plot (min-width:600px)" in (root / "web/css/workbench.css").read_text()
assets = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
          for path in sorted((root / "docs/qa/assets/source-explorer").rglob("*")) if path.is_file()}
assert len(assets) == 10
subprocess.run(["git", "diff", "--check"], cwd=root, check=True, capture_output=True)
print(json.dumps({"protected_paths_changed": protected, "syntax_files": scripts,
                  "valid_local_links": links, "law_entries": 147,
                  "evidence_sha256": assets}, indent=2))
