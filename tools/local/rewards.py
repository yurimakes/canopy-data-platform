"""팀 주간 보상 원장은 유지하고 여정·미션·랭킹 추가 보상만 별도 저장."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from zoneinfo import ZoneInfo
from business import read_rows, current_missions
from services.local_documents import LocalDocuments
from services.trip_service import ApiError
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError


def identity(kind,user,source):
    return hashlib.sha256(json.dumps([kind,user['campaign_id'],user['user_id'],source]).encode()).hexdigest()


def ledger(data):return LocalDocuments(Path(data)/'bonus-rewards.sqlite')


def existing(data,rid):
    try:return ledger(data).read_item(rid)
    except CosmosResourceNotFoundError:return None


def persist(data,record):
    try:return ledger(data).create_item(record)
    except CosmosResourceExistsError:return ledger(data).read_item(record['id'])


def baseline(data,user,at=None):
    bound=(datetime.fromisoformat(at.replace('Z','+00:00')) if at else datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Seoul')).strftime('%G-W%V')
    records=read_rows(Path(data)/'weekly/personal_baseline.json')
    records=[r for r in records if r.get('user_id')==user['user_id'] and r.get('campaign_id')==user['campaign_id'] and r.get('week','')<=bound]
    try:
        override=LocalDocuments(Path(data)/'baseline-test.sqlite').read_item(identity('baseline',user,'test'))
        if override['week']<=bound:records.append(override)
    except CosmosResourceNotFoundError:pass
    records.sort(key=lambda r:r['week'])
    ready=[r for r in records if r.get('status')=='ready' and r.get('baseline_g_co2e_per_km') is not None]
    return ready[-1] if ready else (records[-1] if records else None)


def attach_test_baseline(data,user):
    root=Path(__file__).resolve().parents[2]/'.local-data/scenarios/baseline/weekly'
    report=json.loads((root/'run.json').read_text(encoding='utf-8')) if (root/'run.json').exists() else {}
    if report.get('stages',{}).get('personal_baseline',{}).get('status')!='passed':
        raise ApiError(409,'test_baseline_missing','먼저 Test-Local.cmd -Weekly로 기준 계산을 검증해주세요.')
    rows=[r for r in read_rows(root/'personal_baseline.json') if r.get('status')=='ready']
    if not rows:raise ApiError(409,'test_baseline_missing','검증된 개인 기준이 없습니다.')
    source=max(rows,key=lambda r:r['week'])
    record={**source,'id':identity('baseline',user,'test'),'user_id':user['user_id'],'campaign_id':user['campaign_id'],
            'development_only':True,'source_user_id':source['user_id'],'source':'6명 합성 여정의 실제 Weekly 계산 결과'}
    store=LocalDocuments(Path(data)/'baseline-test.sqlite')
    try:return store.create_item(record)
    except CosmosResourceExistsError:return store.read_item(record['id'])


def trip_comparison(data,user,trip):
    if trip['user_id']!=user['user_id'] or trip['campaign_id']!=user['campaign_id']:raise ApiError(404,'not_found','여정 없음')
    if trip['status']!='ready':return {'status':'processing'}
    b=baseline(data,user,trip['started_at'])
    if not b or b.get('status')!='ready':return {'status':'awaiting_baseline','message':'개인 이동 기준이 준비되면 절감량을 비교할 수 있어요.'}
    confirmed=trip.get('confirmed_trip')
    if not confirmed:raise ApiError(409,'trip_incomplete','확정 여정 결과 없음')
    distance=Decimal(str(confirmed['total_distance_m']))
    actual=Decimal(str(confirmed['total_carbon_kg']))
    reference=Decimal(str(b['baseline_g_co2e_per_km']))*distance/Decimal(1000000)
    return {'status':'weekly_settlement','baseline_kg':float(reference),'actual_kg':float(actual),
        'saved_kg':float(max(Decimal(0),reference-actual)),'baseline_g_per_km':b['baseline_g_co2e_per_km'],
        'baseline_week':b['week'],'development_only':b.get('development_only',False),
        'message':'토큰은 이번 주 전체 이동 결과를 기준으로 주간 정산됩니다.'}


def acknowledge_mission(data,user,assignment_id,trips):
    rid=identity('mission',user,assignment_id);old=existing(data,rid)
    if old:return old
    bundle=current_missions(data,user,trips)
    mission=next((m for m in bundle['missions'] if m['assignment_id']==assignment_id),None)
    if not mission:raise ApiError(404,'mission_not_found','내 미션이 아닙니다.')
    if not mission.get('completed'):raise ApiError(409,'mission_incomplete','목표 달성 후 확인할 수 있어요.')
    return persist(data,{'id':rid,'assignment_id':assignment_id,'user_id':user['user_id'],'campaign_id':user['campaign_id'],
        'title':mission['mission_name'],'status':'paid','kind':'mission','points':extension_policy()['mission_tokens'],'week_start':bundle['week_start'],
        'policy_version':extension_policy()['version'],
        'created_at':datetime.now(timezone.utc).isoformat()})


def acknowledged(data,user):
    return {r['assignment_id'] for r in ledger(data).all() if r.get('kind')=='mission' if r['user_id']==user['user_id'] and r['campaign_id']==user['campaign_id']}


def extension_policy():
    root=Path(__file__).resolve().parents[2]
    return json.loads((root/'shared/configs/local_reward_extensions.json').read_text(encoding='utf-8'))


def bonus_wallet(data,user,weekly_panel):
    rows=[r for r in ledger(data).all() if r['user_id']==user['user_id'] and r['campaign_id']==user['campaign_id'] and r.get('status')=='paid']
    weekly=weekly_panel.get('data',{}) if weekly_panel.get('state')=='ready' else {}
    items=list(weekly.get('items',[]))+[{'id':r['id'],'title':r['title'],'time':r['created_at'],'amount':r['points'],'status':'paid','kind':r.get('kind')} for r in rows]
    items.sort(key=lambda r:r['time'],reverse=True)
    return {'state':'ready','data':{'balance':float(Decimal(str(weekly.get('balance',0)))+sum(Decimal(str(r['points'])) for r in rows)),
        'items':items,'developmentOnly':True}}


def settle_ranking(data):
    # 완료된 집계에서 지난 주의 개인 순위만 사용. 추가 보상 원장은 순위 입력에 넣지 않음
    report=Path(data)/'weekly/run.json'
    if not report.exists():return
    run=json.loads(report.read_text(encoding='utf-8'))
    stages=run.get('stages',{})
    if not stages or stages.get('ranking',{}).get('status')!='passed' or any(s.get('status')!='passed' for s in stages.values()):return
    from services.reward_rules import ranking_points
    current=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%G-W%V');p=extension_policy()
    for row in read_rows(Path(data)/'weekly/ranking.json'):
        if row.get('ranking_type')!='personal' or row['week']>=current:continue
        points=ranking_points(row['rank'],p)
        if points<=0:continue
        persist(data,{'id':identity('ranking',row,row['week']),'kind':'ranking','user_id':row['user_id'],'campaign_id':row['campaign_id'],
            'week':row['week'],'rank':row['rank'],'points':points,'status':'paid','title':f"주간 랭킹 {row['rank']}위 보상",
            'policy_version':p['version'],'created_at':datetime.now(timezone.utc).isoformat()})
