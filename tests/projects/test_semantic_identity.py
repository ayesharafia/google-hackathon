import shutil
from pathlib import Path

import pytest

from physimesh.projects.studies import MODEL_MODULES, model_identity


def test_only_declared_model_dependency_closure_changes_identity(tmp_path):
    from physimesh.projects import studies
    root = Path(studies.__file__).parents[1]
    for name in MODEL_MODULES:
        target = tmp_path/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, target)
    before = model_identity(tmp_path)
    (tmp_path/'projects/reports.py').write_text('# Changed PDF presentation')
    (tmp_path/'api').mkdir(); (tmp_path/'api/app.py').write_text('# Changed HTTP presentation')
    assert model_identity(tmp_path) == before
    path = tmp_path/'drone/atmosphere.py'
    path.write_text(path.read_text()+'\n# Deliberately changed physical dependency\n')
    assert model_identity(tmp_path)['source_fingerprint_sha256'] != before['source_fingerprint_sha256']
    path.unlink()
    with pytest.raises(FileNotFoundError):
        model_identity(tmp_path)
