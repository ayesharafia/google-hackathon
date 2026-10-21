"""An organization switch must not show projects from another active context."""
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings


def test_selected_organization_filters_inventory_and_keyset_pages(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', '', None, hosted_mode=True))
    identity = app.state.identity
    owner = identity.provision('owner@example.test', password='synthetic-password')
    outsider = identity.provision('outsider@example.test', password='synthetic-password')
    left = identity.organization(owner, 'Left fixture organization')
    right = identity.organization(owner, 'Right fixture organization')
    private = identity.organization(outsider, 'Private fixture organization')
    token = identity.login('owner@example.test', 'synthetic-password')['token']
    auth = {'Authorization': 'Bearer '+token}
    expected = {left: set(), right: set()}
    with TestClient(app) as client:
        for org, ids in expected.items():
            for number in range(3):
                response = client.post('/api/drone/projects', headers={**auth, 'X-Organization-ID': org},
                                       json={'title': f'Synthetic design {number}'})
                assert response.status_code == 201, response.text
                ids.add(response.json()['project_id'])
        for org, ids in expected.items():
            seen, cursor = set(), ''
            while True:
                response = client.get('/api/drone/projects', headers={**auth, 'X-Organization-ID': org},
                                      params={'limit': 1, 'after': cursor})
                assert response.status_code == 200, response.text
                page = response.json()
                seen.update(row['project_id'] for row in page['projects'])
                if not page['next_cursor']:
                    break
                cursor = page['next_cursor']
            assert seen == ids
        # Older API clients can still request all their authorized memberships.
        assert {p['project_id'] for p in client.get('/api/drone/projects', headers=auth).json()['projects']} == (
            expected[left] | expected[right])
        for unauthorized in (private, 'org_missing', ''):
            response = client.get('/api/drone/projects', headers={**auth, 'X-Organization-ID': unauthorized})
            assert response.status_code == 403
