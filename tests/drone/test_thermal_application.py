import copy
import json
import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.provenance import sha256_record

request=runpy.run_path(str(Path(__file__).with_name('test_thermal.py')))['request']
PATH='/api/drone/thermal/screen'


@pytest.mark.parametrize('hosted',[False,True])
def test_auth_hash_refusal_schema_nonmutation(tmp_path,hosted):
    app=create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','synthetic-token',None,hosted_mode=hosted))
    with TestClient(app) as c:
        assert c.post(PATH,json=request()).status_code==401
        if hosted:
            app.state.identity.provision('thermal@example.test',password='synthetic-fixture-password')
            token=app.state.identity.login('thermal@example.test','synthetic-fixture-password')['token']
        else:token='synthetic-token'
        h={'Authorization':'Bearer '+token}
        body=request();before=copy.deepcopy(body)
        r=c.post(PATH,json=body,headers=h);assert r.status_code==200
        result=r.json();assert result['status']=='SCREENING_COMPUTED'
        assert result['schema_version']=='thermal_screening_request_v1'
        assert result['inputs']==body and body==before
        assert result['input_sha256']==sha256_record(body)
        digest=result.pop('evaluation_sha256');assert digest==sha256_record(result)
        assert result['evidence_level']=='unverified' and result['aircraft_status'] is None and result['feasibility'] is None
        assert result['outputs']['final_temperature_k']==pytest.approx(336.7879441171442)
        assert result['output_units']['final_temperature_k']=='K'
        assert c.post(PATH,json=body,headers=h).json()==r.json()
        assert c.post(PATH,json=request(initial_temperature_k=401),headers=h).json()['input_sha256']!=result['input_sha256']
        for changes,status in [({'evaluation':'thermal_safety'},'SOLVER_UNSUPPORTED'),({'lumped_biot_number':0.2},'MODEL_INAPPLICABLE'),({'mass_kg':0},'MODEL_INAPPLICABLE'),({'segments':[body['segments'][0]|{'conductance_w_k':-1}]},'MODEL_INAPPLICABLE')]:
            refused=c.post(PATH,json=request(**changes),headers=h)
            assert refused.status_code==200 and refused.json()['status']==status
            assert refused.json()['outputs']=={} and refused.json()['output_units']=={}
        for changes in [{'extra':1},{'mass_kg':True},{'mass_kg':'2'},{'property_source':' '},{'segments':[]},{'segments':[{}]},{'segments':[body['segments'][0]|{'extra':1}]}]:
            invalid=c.post(PATH,json=body|changes,headers=h)
            assert invalid.status_code==422 and invalid.json()=={'detail':'Invalid thermal screening request.'}
        for invalid in ['{broken',json.dumps(body).replace('400','NaN'),json.dumps(body).replace('400','Infinity')]:
            invalid=c.post(PATH,content=invalid,headers=h|{'Content-Type':'application/json'})
            assert invalid.status_code==422 and invalid.json()=={'detail':'Invalid thermal screening request.'}
        assert c.get(PATH,headers=h).status_code==405
        assert c.post(PATH+'/extra',json=body,headers=h).status_code in [403,404]
        assert c.post(PATH,json=body,headers={'Authorization':'Bearer wrong'}).status_code==401
        assert app.state.projects.repository.page()['projects']==[]


def test_cookie_csrf(tmp_path):
    app=create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','synthetic-token',None))
    with TestClient(app) as c:
        assert c.post('/api/session',headers={'Authorization':'Bearer synthetic-token','Origin':'http://testserver'}).status_code==200
        assert c.post(PATH,json=request()).status_code==403
        assert c.post(PATH,json=request(),headers={'Origin':'https://wrong.test'}).status_code==403
        assert c.post(PATH,json=request(),headers={'Origin':'http://testserver'}).status_code==200


@pytest.mark.parametrize('changes',[
    {'mass_kg':1e200,'specific_heat_j_kg_k':1,'initial_temperature_k':2e-300,'segments':[{'duration_s':1e300,'ambient_temperature_k':1e-300,'heat_input_w':0,'conductance_w_k':1e-100}]},
    {'mass_kg':1e-200,'specific_heat_j_kg_k':3e-124,'initial_temperature_k':300,'segments':[{'duration_s':1,'ambient_temperature_k':300,'heat_input_w':5e-324,'conductance_w_k':0}]},
    {'mass_kg':1,'specific_heat_j_kg_k':1,'initial_temperature_k':1e300,'segments':[{'duration_s':750,'ambient_temperature_k':1e-100,'heat_input_w':0,'conductance_w_k':1}]},
])
def test_accepted_numeric_refusals_through_api(tmp_path,changes):
    app=create_app(Settings(tmp_path,tmp_path/'jobs.sqlite','synthetic-token',None))
    with TestClient(app) as c:
        body=request(**changes)
        response=c.post(PATH,json=body,headers={'Authorization':'Bearer synthetic-token'})
        assert response.status_code==200
        r=response.json()
        assert r['status']=='MODEL_INAPPLICABLE' and r['outputs']=={} and r['output_units']=={}
        assert r['evidence_level']=='unverified' and r['aircraft_status'] is None and r['feasibility'] is None
        assert r['input_sha256']==sha256_record(body)
        digest=r.pop('evaluation_sha256');assert digest==sha256_record(r)
