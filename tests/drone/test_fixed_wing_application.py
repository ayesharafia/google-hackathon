import copy
import json
import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.provenance import sha256_record

request=runpy.run_path(str(Path(__file__).with_name('test_fixed_wing.py')))['request']
PATH='/api/drone/fixed-wing/screen'
@pytest.mark.parametrize('hosted',[False,True])
def test_real_app_auth_refusal_hash_nonmutation(tmp_path,hosted):
    app=create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','synthetic-token',None,hosted_mode=hosted))
    with TestClient(app) as c:
        assert c.post(PATH,json=request()).status_code==401
        if hosted:
            app.state.identity.provision('wing@example.test',password='synthetic-fixture-password')
            token=app.state.identity.login('wing@example.test','synthetic-fixture-password')['token']
        else:token='synthetic-token'
        h={'Authorization':'Bearer '+token}
        body=request();before=copy.deepcopy(body);response=c.post(PATH,json=body,headers=h)
        assert response.status_code==200
        result=response.json();assert result['status']=='SCREENING_COMPUTED'
        assert result['inputs']==body and body==before
        assert result['input_sha256']==sha256_record(body)
        digest=result.pop('evaluation_sha256');assert digest==sha256_record(result)
        assert result['outputs']['lift_n']==7500
        assert result['output_units']['drag_power_w']=='W'
        assert result['aircraft_status'] is None and result['feasibility'] is None
        assert result['evidence_level']=='unverified'
        assert response.json()==c.post(PATH,json=body,headers=h).json()
        assert c.post(PATH,json=request(airspeed_m_s=51),headers=h).json()['input_sha256']!=result['input_sha256']
        for changes,status in [({'configuration':'multirotor'},'MODEL_INAPPLICABLE'),({'evaluation':'flight_approval'},'SOLVER_UNSUPPORTED'),({'span_efficiency':0},'MODEL_INAPPLICABLE')]:
            refusal=c.post(PATH,json=request(**changes),headers=h)
            assert refusal.status_code==200 and refusal.json()['status']==status and refusal.json()['outputs']=={}
        for changes in [{'extra':1},{'airspeed_m_s':True},{'airspeed_m_s':'50'},{'coefficient_source':' '},{'coefficient_envelope':{}}]:
            invalid=c.post(PATH,json=body|changes,headers=h)
            assert invalid.status_code==422 and invalid.json()=={'detail':'Invalid fixed-wing screening request.'}
        for invalid in ['{broken',json.dumps(body).replace('50.0','NaN'),json.dumps(body).replace('50.0','Infinity')]:
            r=c.post(PATH,content=invalid,headers=h|{'Content-Type':'application/json'})
            assert r.status_code==422 and r.json()=={'detail':'Invalid fixed-wing screening request.'}
        assert c.get(PATH,headers=h).status_code==405
        assert c.post(PATH+'/extra',json=body,headers=h).status_code in [403,404]
        assert app.state.projects.repository.page()['projects']==[]
        assert c.post(PATH,json=body,headers={'Authorization':'Bearer wrong'}).status_code==401


def test_local_cookie_csrf(tmp_path):
    app=create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','synthetic-token',None))
    with TestClient(app) as c:
        assert c.post('/api/session',headers={'Authorization':'Bearer synthetic-token','Origin':'http://testserver'}).status_code==200
        assert c.post(PATH,json=request()).status_code==403
        assert c.post(PATH,json=request(),headers={'Origin':'https://wrong.test'}).status_code==403
        assert c.post(PATH,json=request(),headers={'Origin':'http://testserver'}).status_code==200
