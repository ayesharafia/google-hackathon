from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings


def test_contract_discovery_is_authenticated_versioned_and_read_only(tmp_path):
    client = TestClient(create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','test-token',None)))
    path = '/api/drone/contracts'
    assert client.get(path).status_code == 401
    auth = {'Authorization':'Bearer test-token'}
    assert 'aircraft_study_v2' in client.get(path,headers=auth).json()['versions']
    assert client.get(path+'/aircraft_study_v2',headers=auth).json()['properties']['schema_version']['const'] == 'aircraft_study_v2'
    assert client.get(path+'/results_v1',headers=auth).status_code == 200
    assert client.get(path+'/v99',headers=auth).status_code == 404
    assert client.post(path,headers=auth,json={}).status_code == 405
