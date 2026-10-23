"""Check that a local wheel contains the exact source explorer and integration assets."""
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
work = Path(tempfile.mkdtemp(prefix="source-explorer-package-", dir=root / ".backend"))
result = subprocess.run(
    ["uv", "build", "--wheel", "--out-dir", str(work)], cwd=root,
    text=True, capture_output=True, timeout=90, check=False,
)
if result.returncode:
    raise RuntimeError((result.stdout + result.stderr)[-3000:])
wheel = next(work.glob("*.whl"))
paths = ["js/source-explorer.js", "js/source-library.js", "js/input-editors.js",
         "js/workbench.js", "css/workbench.css", "workbench.html"]
with zipfile.ZipFile(wheel) as archive:
    build = json.loads(archive.read("physimesh/_build.json"))
    for path in paths:
        resource = "resources/web/" + path
        raw = (root / "web" / path).read_bytes()
        assert archive.read("physimesh/" + resource) == raw, path
        assert build["resources"][resource] == hashlib.sha256(raw).hexdigest(), path
print(json.dumps({"verified_assets": paths,
                  "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                  "limits": "Local wheel bytes and resource hashes only; no deployment."}, indent=2))
