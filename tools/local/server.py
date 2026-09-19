"""로컬 통합 서버. 계정·여정 코드는 재사용하고 저장과 수집만 PC에서 처리."""
from contextlib import contextmanager
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('CANOPY_LOCAL_DATA_DIR', ROOT / '.local-data')).resolve()
sys.path.insert(0, str(ROOT / 'apps/api'))
sys.path.insert(0, str(Path(__file__).parent))
ML_STATE={'status':'loading'}
EXPORT_LOCK=threading.Lock()
WEEKLY_LOCK=threading.Lock()
WEEKLY_PROCESS=None


def configure():
    DATA.mkdir(parents=True, exist_ok=True)
    # 기존 PC의 Azure 설정을 이어받지 않고 실행 모드를 명시적으로 고정
    os.environ.update(APP_ENV='development', CANOPY_LOCAL_ONLY='true', TRIP_STORE='sqlite',
        TRIP_SQLITE_PATH=str(DATA / 'trips.sqlite'), CANOPY_LOCAL_USERS_PATH=str(DATA / 'users.sqlite'),
        TRIP_CAMPAIGN_ID='local_test', CANOPY_ACCOUNT_AUTH_ENABLED='true', TRIP_AUTH_MODE='local',
        TRIP_LOCAL_TOKENS='{}', TRIP_PROCESSOR='server:LocalResultProcessor', TRIP_PROCESS_ON_STOP='false',
        CANOPY_CAMPAIGNS_JSON='{}', TRIP_PROCESS_DELAY_SECONDS='0', TRIP_END_EVENTS_ENABLED='false', TRIP_DATABRICKS_ENABLED='false', TRIP_RESULT_OWNER='functions')
    os.environ.pop('WEBSITE_HOSTNAME', None)
    os.environ.pop('CANOPY_CAMPAIGNS_JSON', None)
    from network_guard import install
    install()


@contextmanager
def database():
    db = sqlite3.connect(DATA / 'events.sqlite', timeout=30)
    db.execute('CREATE TABLE IF NOT EXISTS gps (event_id TEXT PRIMARY KEY, trip_id TEXT, user_id TEXT, sequence INTEGER, body TEXT)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS gps_sequence ON gps(trip_id, user_id, sequence)')
    db.execute('CREATE TABLE IF NOT EXISTS predictions (trip_id TEXT PRIMARY KEY, point_count INTEGER, body TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS ml_results (trip_id TEXT PRIMARY KEY, body TEXT)')
    try:
        with db:
            yield db
    finally:
        db.close()


class LocalResultProcessor:
    def process_trip(self, trip):
        from services.trip_processor import ProcessingError
        with database() as db:
            row = db.execute('SELECT body FROM ml_results WHERE trip_id=?', (trip['trip_id'],)).fetchone()
        if row is None:
            raise ProcessingError('local_ml_not_configured', '실제 모델 또는 ML 결과 입력 필요')
        return json.loads(row[0])


def export_trips():
    with EXPORT_LOCK:
        return _export_trips()


def _export_trips():
    from services.runtime import service
    with service().store.connect() as db:
        # SQLiteTripStore의 저장 구조와 동일한 문서 사용
        rows = db.execute('SELECT payload FROM trips').fetchall()
    trips = [json.loads(row[0]) for row in rows]
    trips = [t for t in trips if t.get('status') and t.get('trip_id') and t.get('type') != 'trip_feedback']
    target = DATA / 'inputs'
    target.mkdir(exist_ok=True)
    (target / 'trips.json').write_text(json.dumps(trips, ensure_ascii=False), encoding='utf-8')
    from services.runtime import user_registration
    from business import MissionRepo,LedgerStore
    (target/'mission_bundles.json').write_text(json.dumps(MissionRepo(DATA).store.all(),ensure_ascii=False),encoding='utf-8')
    (target/'reward_ledger_history.json').write_text(json.dumps(LedgerStore(DATA/'rewards.sqlite').all(),ensure_ascii=False),encoding='utf-8')
    users = [{k:v for k,v in u.items() if k not in ("credentials", "sessions", "login_failures", "_etag")} for u in user_registration().container.all()]
    (target / 'users.json').write_text(json.dumps(users, ensure_ascii=False), encoding='utf-8')
    return trips


def worker():
    from services.runtime import service, feedback_service
    from services.trip_service import iso, utcnow
    import time
    model=None
    try:
        if os.getenv('CANOPY_LOCAL_MODEL','auto')!='import':
            from model import LocalModel,VERSION
            model=LocalModel();ML_STATE.update(status='ready',model_version=VERSION)
        else:ML_STATE.update(status='import_only')
    except Exception as exc:
        ML_STATE.update(status='failed',error=str(exc))
        print('모델 초기화 실패:',str(exc),flush=True)
    processed_counts={}
    while True:
        try:
            api=service()
            with api.store.connect() as db:
                trips=[{**json.loads(r[1]),'_etag':str(r[0])} for r in db.execute("SELECT version,payload FROM trips WHERE json_extract(payload,'$.status') IN ('collecting','processing')")]
            for trip in trips:
                with database() as db:
                    points=[json.loads(r[0]) for r in db.execute('SELECT body FROM gps WHERE trip_id=? AND user_id=? ORDER BY sequence',(trip['trip_id'],trip['user_id']))]
                    found=db.execute('SELECT 1 FROM ml_results WHERE trip_id=?',(trip['trip_id'],)).fetchone()
                stopping=trip['status']=='processing'
                if model and not found:
                    try:
                        if stopping:
                            expected=trip.get('expected_last_sequence')
                            if expected is None or [p['sequence'] for p in points]!=list(range(1,expected+1)):
                                if (utcnow()-__import__('datetime').datetime.fromisoformat(trip['ended_at'])).total_seconds()>60:raise ValueError('종료 GPS 순번과 수집 데이터 불일치')
                                continue
                        if not stopping and (len(points)<2 or len(points)-processed_counts.get(trip['trip_id'],0)<10):continue
                        result=model.result(trip,points)
                        from services.trip_processor import validate_result
                        if stopping:validate_result(trip,result)
                        latest={'model_version':result['model_version'],'mode':result['segments'][-1]['mode'],'confidence':result['segments'][-1]['confidence'],'point_count':len(points),'predicted_at':iso(utcnow())}
                        with database() as db:
                            db.execute('INSERT OR REPLACE INTO predictions VALUES (?,?,?)',(trip['trip_id'],len(points),json.dumps(latest)))
                            if stopping:db.execute('INSERT OR REPLACE INTO ml_results VALUES (?,?)',(trip['trip_id'],json.dumps(result)))
                        processed_counts[trip['trip_id']]=len(points)
                        found=stopping
                    except Exception as exc:
                        if stopping:
                            trip.update(status='failed',failed_step='local_inference',error_message=str(exc),updated_at=iso(utcnow()))
                            api.store.replace(trip)
                        else:
                            with database() as db:db.execute('INSERT OR REPLACE INTO predictions VALUES (?,?,?)',(trip['trip_id'],len(points),json.dumps({'error':str(exc)})))
                        continue
                if stopping and found:
                    api._process([trip]);export_trips()
                    from journey_rewards import settle
                    finished=api.get(trip['trip_id'],trip['user_id'])
                    if finished['status']=='ready':settle(DATA,finished,finished,points)
            feedback_service().recover_pending()
        except Exception as exc:
            print('로컬 처리 오류:',type(exc).__name__,str(exc),flush=True)
        time.sleep(1)


def weekly_run(start=False):
    global WEEKLY_PROCESS
    import subprocess,shutil,uuid
    with WEEKLY_LOCK:
        if WEEKLY_PROCESS and WEEKLY_PROCESS.poll() is None:
            return {'status':'running','message':'PC에서 주간 집계 실행 중입니다.'}
        if not start:return {'status':'idle','exit_code':WEEKLY_PROCESS.poll()} if WEEKLY_PROCESS else {'status':'idle'}
        snapshot=DATA/'runs'/str(uuid.uuid4())/'inputs'
        snapshot.mkdir(parents=True)
        with EXPORT_LOCK:
            _export_trips()
            for path in (DATA/'inputs').glob('*.json'):shutil.copy2(path,snapshot/path.name)
        env=dict(os.environ)
        java=ROOT/'.local-data/runtime/java'
        if java.exists():env['JAVA_HOME']=str(java)
        with (DATA/'weekly.log').open('w',encoding='utf-8') as log:
            WEEKLY_PROCESS=subprocess.Popen([sys.executable,str(ROOT/'tools/local/weekly.py'),'--inputs',str(snapshot),'--output',str(DATA/'weekly'),'--state',str(DATA)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return {'status':'running','message':'주간 집계를 시작했습니다. 완료 후 결과 화면을 새로고침해주세요.'}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data):
        payload = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        # localhost 웹 앱과 동일 LAN의 Expo 개발 앱에서만 사용
        origin = self.headers.get('Origin', '')
        from urllib.parse import urlsplit
        if urlsplit(origin).hostname in ('localhost', '127.0.0.1'):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        from urllib.parse import urlsplit
        origin = self.headers.get('Origin', '')
        if urlsplit(origin).hostname in ('localhost', '127.0.0.1'):
            self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-functions-key')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.end_headers()

    def handle_api(self):
        from services.runtime import accounts, service
        from services.trip_service import ApiError, public
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 2_000_000:
                raise ApiError(413, 'too_large', '요청 크기 초과')
            raw = self.rfile.read(length)
            body = json.loads(raw) if raw else {}
            path = self.path.split('?', 1)[0]
            if path == '/api/local/status':
                return self.send(200, {'environment': 'local', 'azure_enabled': False,
                    'ml': ML_STATE, 'data_directory': str(DATA)})
            if path.startswith('/api/gps/') and self.command=='GET':
                token=self.headers.get('Authorization','').removeprefix('Bearer ')
                user=accounts().authenticated(token)
                tid=path.rsplit('/',1)[-1];service().get(tid,user['user_id'])
                with database() as db:rows=[json.loads(r[0]) for r in db.execute('SELECT body FROM gps WHERE trip_id=? AND user_id=? ORDER BY sequence',(tid,user['user_id']))]
                return self.send(200,{'events':rows})
            if path.startswith('/api/predictions/'):
                token=self.headers.get('Authorization','').removeprefix('Bearer ')
                user=accounts().authenticated(token)
                tid=path.rsplit('/',1)[-1]
                service().get(tid,user['user_id'])
                with database() as db:row=db.execute('SELECT body FROM predictions WHERE trip_id=?',(tid,)).fetchone()
                return self.send(200,json.loads(row[0]) if row else {'status':'waiting','model':ML_STATE})
            if path.startswith(('/api/local/','/api/comparison/','/api/missions/','/api/journey/')) or path in ('/api/community', '/api/trips'):
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                user = accounts().authenticated(token)
                if path.startswith('/api/local/') and user['role'] != 'developer':
                    raise ApiError(403, 'forbidden', '개발자 전용 기능')
                if path == '/api/local/scenario' and self.command=='GET':
                    from scenario_view import panels
                    return self.send(200,panels())
                if path == '/api/local/reward-demo' and self.command=='POST':
                    from reward_demo import create
                    return self.send(201,create(DATA,user))
                if path == '/api/local/baseline-test' and self.command=='POST':
                    from rewards import attach_test_baseline
                    return self.send(200,attach_test_baseline(DATA,user))
                if path == '/api/local/route-preview' and self.command=='POST':
                    from journey_rewards import test_quote
                    return self.send(200,test_quote(DATA,user,body.get('route')))
                if path == '/api/journey/quote' and self.command=='POST':
                    from journey_rewards import route_quote
                    return self.send(200,route_quote(DATA,user,body['from'],body['to'],body.get('direction','outbound')))
                if path == '/api/journey/places' and self.command=='POST':
                    from population import search
                    return self.send(200,{'places':search(body.get('query',''))})
                if path == '/api/journey/prepare' and self.command=='POST':
                    from journey_rewards import prepare
                    prepare(DATA,user,body.get('quote_id'))
                    return self.send(200,{'status':'prepared'})
                if path.startswith('/api/comparison/') and self.command=='GET':
                    from journey_rewards import settle
                    trip=service().get(path.rsplit('/',1)[-1],user['user_id'])
                    with database() as db:
                        points=[json.loads(r[0]) for r in db.execute('SELECT body FROM gps WHERE trip_id=? ORDER BY sequence',(trip['trip_id'],))]
                    return self.send(200,settle(DATA,user,trip,points))
                if path == '/api/missions/acknowledge' and self.command=='POST':
                    from rewards import acknowledge_mission
                    return self.send(200,acknowledge_mission(DATA,user,body['assignment_id'],export_trips()))
                if path == '/api/local/weekly':
                    return self.send(202 if self.command=='POST' else 200,weekly_run(self.command=='POST'))
                if path == '/api/local/ml-result' and self.command == 'POST':
                    result = body.get('result', body)
                    owner=body.get('trip',{}).get('user_id',body.get('user_id',user['user_id']))
                    trip = service().get(result['trip_id'], owner)
                    from services.trip_processor import validate_result
                    if trip['status'] != 'processing':
                        raise ApiError(409, 'trip_not_processing', '종료된 처리 대기 여정만 입력 가능')
                    try:
                        validate_result(trip, result)
                    except Exception as exc:
                        raise ApiError(400, 'invalid_ml_result', str(exc)) from exc
                    with database() as db:
                        seqs = [r[0] for r in db.execute('SELECT sequence FROM gps WHERE trip_id=? AND user_id=? ORDER BY sequence', (trip['trip_id'], trip['user_id']))]
                        if seqs != list(range(1, trip.get('expected_last_sequence', 0) + 1)) or not seqs:
                            raise ApiError(409, 'gps_incomplete', 'GPS 시퀀스 누락 확인 필요')
                        db.execute('INSERT OR REPLACE INTO ml_results VALUES (?,?)', (trip['trip_id'], json.dumps(result)))
                    return self.send(202, {'status': 'accepted'})
                if path == '/api/local/export' and self.command == 'POST':
                    return self.send(200, {'trip_count': len(export_trips())})
                if path == '/api/community':
                    from projections import community
                    from business import current_missions
                    trips=export_trips()
                    result=community(DATA,user)
                    bundle=current_missions(DATA,user,trips)
                    from projections import mission_panel
                    from rewards import acknowledged,baseline
                    result['missions']=mission_panel(bundle,acknowledged(DATA,user))
                    b=baseline(DATA,user)
                    if b and b.get('status')=='ready':
                        result['baseline']={'state':'ready','data':{**result.get('baseline',{}).get('data',{}),'status':'ready','personalKg':b['baseline_g_co2e_per_km'],
                            'globalKg':result.get('baseline',{}).get('data',{}).get('globalKg'),'unit':'gCO₂e/km','updatedAt':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'reason':'개인 이동 기준 준비 완료',
                            'developmentOnly':b.get('development_only',False),'trips':b.get('confirmed_trip_count',0),
                            'observationDays':b.get('observation_days',0),'source':b.get('source','Weekly 개인 기준')}}
                    if result['baseline']['state']=='empty':
                        result['baseline']={'state':'ready','data':{'status':'collecting','personalKg':None,'globalKg':None,'unit':'gCO₂e/km','updatedAt':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'reason':'유효한 여정과 관찰 기간이 쌓이면 주간 집계에서 개인 기준을 만들어요.'}}
                    from rewards import settle_ranking,bonus_wallet
                    settle_ranking(DATA)
                    result['rewards']=bonus_wallet(DATA,user,result['rewards'])
                    return self.send(200,result)
                if path == '/api/trips':
                    return self.send(200, {'trips': [public(t) for t in export_trips() if t['user_id'] == user['user_id']]})
            if path == '/api/gps' and self.command == 'POST':
                if self.headers.get('x-functions-key') != os.environ['CANOPY_LOCAL_GPS_KEY']:
                    raise ApiError(401, 'unauthorized', '로컬 GPS 키 확인 필요')
                trip = service().get(body['trip_id'], body['user_id'])
                if body.get('device_id') != trip['device_id']:
                    raise ApiError(403, 'forbidden', '다른 기기의 여정')
                from math import isfinite
                if not isinstance(body.get('sequence'), int) or isinstance(body['sequence'], bool) or body['sequence'] < 1:
                    raise ApiError(400, 'invalid_sequence', 'GPS 순번 확인 필요')
                for name, bound in [('lat',90), ('lon',180)]:
                    v=body.get(name)
                    if isinstance(v,bool) or not isinstance(v,(float,int)) or not isfinite(v) or abs(v)>bound:
                        raise ApiError(400, 'invalid_coordinate', 'GPS 좌표 확인 필요')
                from services.trip_processor import timestamp
                timestamp(body['event_time'])
                with database() as db:
                    old = db.execute('SELECT body FROM gps WHERE event_id=? OR (trip_id=? AND user_id=? AND sequence=?)',
                        (body['event_id'],body['trip_id'],body['user_id'],body['sequence'])).fetchone()
                    if old and json.loads(old[0]) != body:
                        raise ApiError(409, 'gps_conflict', '동일 GPS 식별자에 다른 데이터')
                    if not old:
                        if trip['status'] != 'collecting':
                            raise ApiError(409, 'trip_closed', '종료된 여정')
                        db.execute('INSERT INTO gps VALUES (?,?,?,?,?)', (body['event_id'],body['trip_id'],body['user_id'],body['sequence'],json.dumps(body)))
                return self.send(202, {'status':'accepted','event_id':body['event_id'],'trip_id':body['trip_id']})
            if path.startswith('/api/routes/'):
                raise ApiError(503, 'offline_routes', '로컬 모드에서는 외부 길찾기를 사용하지 않습니다. 경로 없이 여정을 시작해주세요.')
            from trip_routes import dispatch
            code, result = dispatch(self.command, path, dict(self.headers), raw)
            if path=='/api/trips/start' and 200<=code<300:
                from journey_rewards import bind
                bind(DATA,result,result['trip_id'])
            self.send(code, result)
        except ApiError as exc:
            self.send(exc.status, {'status':exc.code,'message':str(exc)})
        except (ValueError, KeyError, TypeError):
            self.send(400, {'status':'invalid_request','message':'입력 형식 확인 필요'})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.send(500, {'status':'local_error','message':type(exc).__name__})

    do_GET = do_POST = do_PATCH = handle_api


def main():
    configure()
    parser=argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args=parser.parse_args()
    import secrets
    settings=DATA/'local-settings.json'
    if not settings.exists():
        settings.write_text(json.dumps({'gps_key':secrets.token_urlsafe(32),'developer_password':secrets.token_urlsafe(18)}))
    credentials=json.loads(settings.read_text())
    os.environ['CANOPY_LOCAL_GPS_KEY']=credentials['gps_key']
    from services.runtime import accounts
    from services.accounts import account_id
    if accounts().read(account_id('canopydev')) is None:
        accounts().signup({'email':'canopydev','password':credentials['developer_password'],'nickname':'로컬 개발자','campaign_code':'TEST'}, developer=True)
    with database():
        pass
    threading.Thread(target=worker, daemon=True).start()
    print(f'로컬 API http://{args.host}:{args.port} / Azure 연결 차단', flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()


if __name__=='__main__':
    sys.modules['server']=sys.modules[__name__]
    main()
