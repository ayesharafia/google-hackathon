import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.provenance import sha256_record

BODY={'configuration':'fixed_wing','evaluation':'atmosphere','altitude_m':20000,'altitude_kind':'geopotential'}
PATH='/api/drone/evaluations/evaluate'
CAT='/api/drone/evaluations/catalog'
@pytest.mark.parametrize('hosted',[False,True])
def test_real_app_auth_evidence_refusal_and_no_mutation(tmp_path,hosted):
    app=create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','synthetic-token',None,hosted_mode=hosted))
    with TestClient(app) as client:
        assert client.get(CAT).status_code==401
        assert client.post(PATH,json=BODY).status_code==401
        if hosted:
            app.state.identity.provision('registry@example.test',password='synthetic-test-password')
            token=app.state.identity.login('registry@example.test','synthetic-test-password')['token']
        else:token='synthetic-token'
        headers={'Authorization':'Bearer '+token}
        catalog=client.get(CAT,headers=headers)
        assert catalog.status_code==200
        assert len(catalog.json()['configurations'])==8
        assert all(not c['aircraft_solver_supported'] for c in catalog.json()['configurations'])
        a=client.post(PATH,json=BODY,headers=headers)
        assert a.status_code==200
        data=a.json();assert data['status']=='REFERENCE_COMPUTED'
        assert data['feasibility'] is None and data['aircraft_status'] is None
        assert data['evidence_level']=='unverified'
        assert data['inputs']==BODY and data['input_sha256']==sha256_record(BODY)
        assert data['output_units']['pressure_pa']=='Pa'
        digest=data.pop('evaluation_sha256');assert digest==sha256_record(data)
        assert a.json()==client.post(PATH,json=BODY,headers=headers).json()
        changed=client.post(PATH,json=BODY|{'altitude_m':21000},headers=headers).json()
        assert changed['input_sha256']!=a.json()['input_sha256']
        assert changed['evaluation_sha256']!=a.json()['evaluation_sha256']
        unsupported=client.post(PATH,json=BODY|{'evaluation':'aircraft_feasibility'},headers=headers)
        assert unsupported.status_code==200 and unsupported.json()['status']=='SOLVER_UNSUPPORTED'
        assert unsupported.json()['outputs']=={} and unsupported.json()['aircraft_status'] is None
        for invalid in [{},{'altitude_m':'20000'},{'altitude_m':True},{'altitude_m':30001},{'outputs':[]},{'outputs':['lift_N']},{'extra':1}]:
            response=client.post(PATH,json=BODY|invalid if invalid else {},headers=headers)
            assert response.status_code==422
            assert response.json()=={'detail':'Invalid evaluation request.'}
        for value in ['NaN','Infinity','-Infinity']:
            raw=json.dumps(BODY).replace('20000',value)
            response=client.post(PATH,content=raw,headers=headers|{'Content-Type':'application/json'})
            assert response.status_code==422 and response.json()=={'detail':'Invalid evaluation request.'}
        assert client.post(PATH,content='{bad',headers=headers|{'Content-Type':'application/json'}).status_code==422
        assert app.state.projects.repository.page()['projects']==[]
        assert client.get(CAT,headers={'Authorization':'Bearer wrong'}).status_code==401
        if hosted:
            assert client.post(PATH+'/',json=BODY,headers=headers,follow_redirects=False).status_code==403
            assert client.get(CAT+'/secret',headers=headers).status_code==403
            assert client.post('/api/drone/screening',json={},headers=headers).status_code==403

def test_local_browser_cookie_csrf_preserved(tmp_path):
    app=create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','synthetic-token',None))
    with TestClient(app) as client:
        session=app.state.browser_sessions.issue()
        client.cookies.set('physicore_browser',session,path='/api')
        assert client.get(CAT).status_code==200
        assert client.post(PATH,json=BODY).status_code==403
        assert client.post(PATH,json=BODY,headers={'Origin':'https://evil.example'}).status_code==403
        assert client.post(PATH,json=BODY,headers={'Origin':'http://testserver'}).status_code==200
