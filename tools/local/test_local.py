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

ROOT=Path(__file__).resolve().parents[2]


def test_local_api(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env={**os.environ,'CANOPY_LOCAL_DATA_DIR':str(tmp_path)}
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
        stopped=request(f'trips/{tid}/stop',{'expected_last_sequence':1},token,expected=202)
        request(f'trips/{tid}',token=new['access_token'],expected=403)
        time.sleep(1)
        assert request(f'trips/{tid}',token=token)['status']=='processing'
        # 연결 검증용 명시적 ML 결과. 실제 추론 성능 테스트가 아님
        result={'trip_id':tid,'model_version':'integration-fixture','segments':[{'segment_id':tid+':1','mode':'walk','start_time':trip['started_at'],'end_time':stopped['ended_at'],'distance_m':100,'confidence':None}]}
        request('local/ml-result',{'result':result},token,expected=202)
        for _ in range(30):
            final=request(f'trips/{tid}',token=token)
            if final['status']=='ready':break
            assert final['status']!='failed',final
            time.sleep(.2)
        assert final['status']=='ready',final
        assert final['confirmed_trip']['total_distance_m']==100
        request(f'trips/{tid}/feedback',{'request_id':str(uuid.uuid4()),'has_issue':False,'feedback_text':None},token)
        request('local/export',{},token)
        users=json.loads((tmp_path/'inputs/users.json').read_text(encoding='utf-8'))
        assert all('credentials' not in u and 'sessions' not in u for u in users)
        trips=json.loads((tmp_path/'inputs/trips.json').read_text(encoding='utf-8'))
        assert len(trips)==1
        request('community',token=token)
    finally:
        process.terminate();process.wait(timeout=10);log.close()


def test_external_connections_blocked():
    code="import sys;sys.path.insert(0,'tools/local');from network_guard import install;install();import socket;socket.create_connection(('example.com',443))"
    result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode!=0
    assert 'RuntimeError' in result.stderr
