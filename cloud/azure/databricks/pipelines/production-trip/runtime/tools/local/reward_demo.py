"""개발자 계정 전용 합성 GPS 재생. 실제 모델·Trip 계산·보상 경로 검증."""
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4
from services.trip_service import TripService
from services.runtime import service
from journey_rewards import route_quote, prepare, bind, settle


def create(data,user):
    from model import LocalModel
    from server import database, export_trips
    now=datetime.now(timezone.utc)
    start=now-timedelta(minutes=25)
    origin={'name':'테스트 출발지','latitude':37.5,'longitude':127.0}
    destination={'name':'테스트 도착지','latitude':37.518,'longitude':127.0}
    quote=route_quote(data,user,origin,destination)
    prepare(data,user,quote['quoteId'])
    # 전역 서버 시계는 변경하지 않고 이 시나리오의 시작 시각만 주입
    api=service()
    creator=TripService(api.store,api.processor,clock=lambda:start,campaign_id=user['campaign_id'])
    trip,_=creator.start(user['user_id'],{'request_id':str(uuid4()),'device_id':'local-reward-demo'},campaign_id=user['campaign_id'],start_context={'simulation':True})
    bind(data,user,trip['trip_id'])
    started=datetime.fromisoformat(trip['started_at'])
    points=[{'event_id':str(uuid4()),'trip_id':trip['trip_id'],'user_id':user['user_id'],'device_id':'local-reward-demo',
             'sequence':i+1,'event_time':(started+timedelta(seconds=i*12)).isoformat(),
             'lat':37.5+.018*i/125,'lon':127.0,'accuracy':5,'is_simulated':True} for i in range(126)]
    with database() as db:
        for p in points:db.execute('INSERT INTO gps VALUES (?,?,?,?,?)',(p['event_id'],p['trip_id'],p['user_id'],p['sequence'],json.dumps(p)))
    # 실제 추론 결과를 먼저 저장한 뒤 종료 처리. 백그라운드 워커와 같은 결과 계약 사용
    result=LocalModel().result({**trip,'ended_at':points[-1]['event_time']},points)
    with database() as db:db.execute('INSERT INTO ml_results VALUES (?,?)',(trip['trip_id'],json.dumps(result)))
    stopped=api.stop(trip['trip_id'],user['user_id'],{'expected_last_sequence':126,'ended_at':points[-1]['event_time']})
    # 워커의 회수를 기다리지 않고 기존 claim 로직으로 처리
    api._process([stopped])
    final=api.get(trip['trip_id'],user['user_id'])
    if final['status']!='ready':raise ValueError('테스트 여정 처리 실패')
    final['is_mock']=True
    final['confirmed_trip']['is_mock']=True
    final['simulation_source']='developer-reward-demo'
    final=api.store.replace(final)
    settle(data,user,final,points)
    prepare(data,user,None)
    export_trips()
    from services.trip_service import public
    return public(final)
