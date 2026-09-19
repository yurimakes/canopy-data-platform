import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
import pytest
from datetime import datetime,timedelta
import shutil

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('model_mode',['import','auto'])
def test_local_api(tmp_path,model_mode):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env={**os.environ,'CANOPY_LOCAL_DATA_DIR':str(tmp_path),'CANOPY_LOCAL_MODEL':model_mode}
    log=(tmp_path/'server.log').open('w',encoding='utf-8')
    process=subprocess.Popen([sys.executable,str(ROOT/'tools/local/server.py'),'--host','127.0.0.1','--port',str(port)],env=env,stdout=log,stderr=log)
    def request(path,body=None,token=None,key=None,expected=200):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        if key:headers['x-functions-key']=key
        req=urllib.request.Request(f'http://127.0.0.1:{port}/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:response=urllib.request.urlopen(req,timeout=10)
        except urllib.error.HTTPError as exc:response=exc
        with response:
            result=json.loads(response.read()); assert response.status==expected,result
            return result
    try:
        for _ in range(60):
            try:request('local/status');break
            except OSError:time.sleep(.2)
        else:raise AssertionError('Server failed to start')
        if model_mode=='auto':
            for _ in range(120):
                state=request('local/status')['ml']
                if state['status']=='ready':break
                assert state['status']!='failed',state
                time.sleep(.5)
            assert state['status']=='ready',state
        creds=json.loads((tmp_path/'local-settings.json').read_text())
        session=request('auth/login',{'email':'canopydev','password':creds['developer_password']})
        token=session['access_token']; uid=session['profile']['id']
        new=request('auth/signup',{'email':'test@example.com','password':'Local-testing-1234','nickname':'Test','campaign_code':'TEST'},expected=201)
        request('auth/signup',{'email':'bad@example.com','password':'Local-testing-1234','nickname':'Test','campaign_code':'WRONG'},expected=400)
        trip=request('trips/start',{'request_id':str(uuid.uuid4()),'device_id':'local-test-device'},token,expected=201)
        tid=trip['trip_id']
        gps={'event_id':str(uuid.uuid4()),'trip_id':tid,'user_id':uid,'device_id':'local-test-device','sequence':1,'event_time':trip['started_at'],'lat':37.5,'lon':127.0}
        request('gps',gps,key=creds['gps_key'],expected=202)
        request('gps',gps,key=creds['gps_key'],expected=202)
        request('gps',{**gps,'lat':38.0},key=creds['gps_key'],expected=409)
        count=1
        if model_mode=='auto':
            for i in range(2,31):
                point={**gps,'event_id':str(uuid.uuid4()),'sequence':i,'lat':37.5+(i-1)*.00001,'event_time':(datetime.fromisoformat(trip['started_at'])+timedelta(seconds=i-1)).isoformat()}
                request('gps',point,key=creds['gps_key'],expected=202)
            count=30
        stopped=request(f'trips/{tid}/stop',{'expected_last_sequence':count,'ended_at':point['event_time']} if model_mode=='auto' else {'expected_last_sequence':1},token,expected=202)
        request(f'trips/{tid}',token=new['access_token'],expected=403)
        if model_mode=='import':
            time.sleep(1)
            assert request(f'trips/{tid}',token=token)['status']=='processing'
        # 연결 검증용 명시적 ML 결과. 실제 추론 성능 테스트가 아님
        result={'trip_id':tid,'model_version':'integration-fixture','segments':[{'segment_id':tid+':1','mode':'walk','start_time':trip['started_at'],'end_time':stopped['ended_at'],'distance_m':100,'confidence':None}]}
        if model_mode=='import':request('local/ml-result',{'result':result},token,expected=202)
        for _ in range(100):
            final=request(f'trips/{tid}',token=token)
            if final['status']=='ready':break
            assert final['status']!='failed',final
            time.sleep(.2)
        assert final['status']=='ready',final
        if model_mode=='import':assert final['confirmed_trip']['total_distance_m']==100
        else:
            assert final['model_version'].startswith('local-speedtransformer')
            assert 31<final['confirmed_trip']['total_distance_m']<34
            assert request('predictions/'+tid,token=token)['point_count']==30
        request(f'trips/{tid}/feedback',{'request_id':str(uuid.uuid4()),'has_issue':False,'feedback_text':None},token)
        request('local/export',{},token)
        users=json.loads((tmp_path/'inputs/users.json').read_text(encoding='utf-8'))
        assert all('credentials' not in u and 'sessions' not in u for u in users)
        trips=json.loads((tmp_path/'inputs/trips.json').read_text(encoding='utf-8'))
        assert len(trips)==1
        panel=request('community',token=token)
        assert len(panel['missions']['data']['items'])==4
        if model_mode=='auto':
            request('local/reward-demo',{},new['access_token'],expected=403)
            demo=request('local/reward-demo',{},token,expected=201)
            assert demo['status']=='ready' and demo['is_mock'] is True
            comparison=request('comparison/'+demo['trip_id'],token=token)
            assert comparison['status']=='paid' and comparison['points']>0
            assert comparison['model_version'].startswith('ktdb-population-')
            assert request('comparison/'+demo['trip_id'],token=token)['id']==comparison['id']
            missions=request('community',token=token)['missions']['data']['items']
            earned=next(m for m in missions if m['status']=='claimable')
            paid=request('missions/acknowledge',{'assignment_id':earned['id']},token)
            again=request('missions/acknowledge',{'assignment_id':earned['id']},token)
            assert paid['id']==again['id']
            assert request('community',token=token)['rewards']['data']['balance']==comparison['points']+paid['points']
            request('local/export',{},token)
            target=ROOT/'.local-data/end-to-end/inputs';target.mkdir(parents=True,exist_ok=True)
            for source in (tmp_path/'inputs').glob('*.json'):shutil.copy2(source,target/source.name)
    finally:
        process.terminate();process.wait(timeout=10);log.close()


def test_external_connections_blocked():
    code="import sys;sys.path.insert(0,'tools/local');from network_guard import install;install();import socket;socket.create_connection(('example.com',443))"
    result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode!=0
    assert 'RuntimeError' in result.stderr
