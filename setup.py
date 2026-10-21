"""Package source web assets and a deterministic resource manifest in application wheels."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class ReleaseBuild(build_py):
    def run(self):
        package = Path(self.build_lib)/'physimesh'
        if package.exists():
            shutil.rmtree(package)
        super().run()
        root = Path(__file__).parent
        (package/'_build.json').unlink(missing_ok=True)
        shutil.copytree(root/'web', package/'resources/web', dirs_exist_ok=True)
        files = {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(package.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
        try:
            revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
            dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip())
        except (OSError, subprocess.CalledProcessError):
            revision, dirty = os.environ.get('PHYSIMESH_BUILD_REVISION', 'unrecorded'), True
        record = {'schema_version': 'application_build_v1', 'revision': revision, 'dirty': dirty,
                  'resources': files, 'dependencies_sha256': hashlib.sha256(
                      (root/'requirements-runtime.lock').read_bytes()).hexdigest()}
        raw = json.dumps(record, sort_keys=True, separators=(',', ':')).encode()
        record['build_sha256'] = hashlib.sha256(raw).hexdigest()
        (package/'_build.json').write_text(json.dumps(record, sort_keys=True)+'\n')


setup(cmdclass={'build_py': ReleaseBuild})
