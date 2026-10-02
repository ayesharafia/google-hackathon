import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.postpro.result_contract import assemble_results

AUTH = {'Authorization': 'Bearer test-token'}
ID = 'c'*16


def package(tmp_path):
    group = {'label': 'VERIFICATION CASE: sphere Re=100', 'code_version': 'a'*40,
             'image_digest': 'image@sha256:'+'b'*64, 'Re': 100, 'D_m': 1,
             'rho_ref_kg_m3': 1, 'nu_m2_s': .01, 'u_inf_m_s': [1, 0, 0]}
    loads = {'run_group_sha256': 'c'*64, 'runs': [{'level': level, 'cd': 1.1,
              'reconciliation': {'status': 'diagnostic_only'}, 'convergence': {'passed': True}}
             for level in ('coarse', 'medium', 'fine')], 'mesh_study': {'behaviour': 'oscillatory'}}
    result = assemble_results(group, loads, [])
    root = tmp_path/'results'/ID; root.mkdir(parents=True)
    data = {'results.json': json.dumps(result).encode(), 'run_group.json': json.dumps(group).encode(),
            'plots/pressure.png': b'\x89PNG\r\n\x1a\nfixture', 'recipes/pressure.json': b'{"status":"diagnostic_only"}'}
    for name, raw in data.items():
        path = root/name; path.parent.mkdir(exist_ok=True); path.write_bytes(raw)
    (root/'hashes.json').write_text(json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in data.items()}))
    return TestClient(create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'test-token', None))), root


@pytest.mark.parametrize('path', [f'/api/drone/results/{ID}', f'/api/drone/runs/{ID}',
                                f'/api/drone/plots/{ID}/pressure.png', f'/api/drone/runs/{ID}/export'])
def test_result_namespace_requires_auth(tmp_path, path):
    client, _ = package(tmp_path)
    assert client.get(path).status_code == 401


def test_export_retains_diagnostics_and_hashes_all_contents(tmp_path):
    client, _ = package(tmp_path)
    response = client.get(f'/api/drone/runs/{ID}/export', headers=AUTH)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        hashes = json.loads(archive.read('hashes.json'))
        assert set(archive.namelist()) == {*hashes, 'hashes.json'}
        for name, digest in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        assert json.loads(archive.read('results.json'))['status'] == 'diagnostic_only'
    assert client.get(f'/api/drone/results/{ID}', headers=AUTH).json()['status'] == 'diagnostic_only'


def test_corrupt_plot_is_refused_in_api_and_export(tmp_path):
    client, root = package(tmp_path)
    (root/'plots/pressure.png').write_bytes(b'changed')
    assert client.get(f'/api/drone/plots/{ID}/pressure.png', headers=AUTH).status_code == 409
    assert client.get(f'/api/drone/runs/{ID}/export', headers=AUTH).status_code == 409


def test_results_inventory_and_missing_group(tmp_path):
    client, _ = package(tmp_path)
    response = client.get('/api/drone/results', headers=AUTH)
    assert response.status_code == 200 and response.json()['groups'][0]['run_group_id'] == ID
    assert client.get('/api/drone/results/'+'a'*16, headers=AUTH).status_code == 404
