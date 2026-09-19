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
    users = [{k:v for k,v in u.items() if k not in ("credentials", "sessions", "login_failures", "_etag")} for u in user_registration().container.all()]
    (target / 'users.json').write_text(json.dumps(users, ensure_ascii=False), encoding='utf-8')
    return trips


def worker():
    from services.runtime import service, feedback_service
    import time
    while True:
        try:
            api = service()
            # 모델 미연결이면 가짜 결과로 완료하지 않고 입력 대기 상태 유지
            from services.trip_service import iso, utcnow
            for trip in api.store.pending(iso(utcnow())):
                with database() as db:
                    found = db.execute('SELECT 1 FROM ml_results WHERE trip_id=?', (trip['trip_id'],)).fetchone()
                if found:
                    api._process([trip])
                    export_trips()
            feedback_service().recover_pending()
        except Exception as exc:
            print('로컬 처리 오류:', type(exc).__name__, str(exc), flush=True)
        time.sleep(1)


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
                    'ml': 'result_import_required', 'data_directory': str(DATA)})
            if path.startswith('/api/local/') or path in ('/api/community', '/api/trips'):
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                user = accounts().authenticated(token)
                if path.startswith('/api/local/') and user['role'] != 'developer':
                    raise ApiError(403, 'forbidden', '개발자 전용 기능')
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
                    return self.send(200, community(DATA, user))
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
