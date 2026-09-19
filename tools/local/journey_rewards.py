"""출발 전 기준 스냅샷과 도착 검증. 로컬 저장 어댑터."""
from datetime import datetime,timezone,timedelta
import uuid
from pathlib import Path
from services.local_documents import LocalDocuments
from services.trip_service import ApiError
from services.reward_rules import journey_points
from azure.cosmos.exceptions import CosmosResourceNotFoundError,CosmosResourceExistsError
from rewards import extension_policy,identity,persist,existing
from model import distance


def store(data):return LocalDocuments(Path(data)/'journey-quotes.sqlite')


def test_quote(data,user,route):
    # 모델 파일 미제공 시에도 지급 연동을 검증하기 위한 명시적 합성 경로
    route=route or {'from':{'name':'테스트 출발지','latitude':37.5,'longitude':127},'to':{'name':'테스트 도착지','latitude':37.518,'longitude':127},'distance_m':2000,'minutes':25,'legs':[]}
    for key in ('from','to'):
        p=route[key]
        if not -90<=float(p['latitude'])<=90 or not -180<=float(p['longitude'])<=180:raise ValueError('invalid coordinates')
    meters=float(route['distance_m'])
    if not 0<meters<=100000:raise ValueError('invalid distance')
    quote={'id':str(uuid.uuid4()),'user_id':user['user_id'],'campaign_id':user['campaign_id'],'route':route,
        'expected_kg':meters/1000*165.91/1000,'source':'테스트용 합성 Population 기준 · 실제 KTDB 추론 아님',
        'development_only':True,'model_version':'fixture-population-v1','policy':extension_policy(),
        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    store(data).create_item(quote)
    return {**route,'id':quote['id'],'quoteId':quote['id'],'expectedKg':quote['expected_kg'],'baselineSource':quote['source'],
        'provider':'local-test','searchedAt':datetime.now(timezone.utc).isoformat(),'fare':None}


def route_quote(data,user,origin,destination,direction='outbound'):
    for p in (origin,destination):
        if not -90<=float(p['latitude'])<=90 or not -180<=float(p['longitude'])<=180:raise ValueError('invalid coordinates')
    meters=distance({'lat':origin['latitude'],'lon':origin['longitude']},{'lat':destination['latitude'],'lon':destination['longitude']})
    if not 10<=meters<=100000:raise ApiError(400,'invalid_distance','출발지와 도착지는 10m 이상, 100km 이내로 선택해주세요.')
    route={'from':origin,'to':destination,'distance_m':meters,'minutes':round(meters/70),'legs':[]}
    from population import estimate
    baseline=estimate(route,direction)
    quote={**baseline,'id':str(uuid.uuid4()),'user_id':user['user_id'],'campaign_id':user['campaign_id'],
        'route':route,'direction':direction,'development_only':True,'policy':extension_policy(),
        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    store(data).create_item(quote)
    return {**route,'id':quote['id'],'quoteId':quote['id'],'expectedKg':quote['expected_kg'],'baselineSource':quote['source'],
        'provider':'local-test','searchedAt':datetime.now(timezone.utc).isoformat(),'fare':None}


def prepare(data,user,quote_id):
    s=store(data);key=identity('intent',user,'next')
    quote=None
    if quote_id:
        try:quote=s.read_item(quote_id)
        except CosmosResourceNotFoundError:raise ApiError(404,'quote_not_found','저장된 경로가 없습니다. 다시 선택해주세요.')
        if quote['user_id']!=user['user_id'] or quote['campaign_id']!=user['campaign_id']:raise ApiError(403,'forbidden','다른 사용자의 경로')
        if datetime.fromisoformat(quote['expires_at'])<datetime.now(timezone.utc):raise ApiError(409,'expired','경로 기준을 다시 확인해주세요.')
    item={'id':key,'quote':quote}
    try:s.create_item(item)
    except CosmosResourceExistsError:
        old=s.read_item(key);s.replace_item(key,item,etag=old['_etag'])


def bind(data,user,trip_id):
    s=store(data)
    try:intent=s.read_item(identity('intent',user,'next'))
    except CosmosResourceNotFoundError:return
    if intent['quote'] and datetime.fromisoformat(intent['quote']['expires_at'])<datetime.now(timezone.utc):
        raise ApiError(409,'expired','경로 기준을 다시 확인해주세요.')
    try:s.create_item({'id':'trip:'+trip_id,'quote':intent['quote']})
    except CosmosResourceExistsError:pass


def settle(data,user,trip,points):
    rid=identity('trip',user,trip['trip_id']);old=existing(data,rid)
    if old:return old
    if trip['status']!='ready':return {'status':'processing'}
    try:q=store(data).read_item('trip:'+trip['trip_id'])['quote']
    except CosmosResourceNotFoundError:q=None
    if not q:return {'status':'no_route','message':'경로 없이 기록한 여정입니다. 여정 보상 기준은 없으며 주간 분석에는 반영됩니다.'}
    if q['user_id']!=user['user_id'] or q['campaign_id']!=user['campaign_id']:raise ApiError(403,'forbidden','다른 사용자의 여정')
    def stamp(v):return datetime.fromisoformat(v.replace('Z','+00:00'))
    valid=sorted([p for p in points if stamp(trip['started_at'])<=stamp(p['event_time'])<=stamp(trip['ended_at'])],key=lambda p:stamp(p['event_time']))
    if len(valid)<2:return {'status':'insufficient_gps','message':'출발·도착을 확인할 GPS가 부족합니다.'}
    def point(p):return {'lat':p['latitude'],'lon':p['longitude']}
    radius=q['policy']['endpoint_radius_m']
    if distance(valid[0],point(q['route']['from']))>radius or distance(valid[-1],point(q['route']['to']))>radius:
        return {'status':'route_incomplete','message':'지정한 출발지·도착지 200m 이내에서 시작하고 마쳐야 여정 보상을 받을 수 있어요.'}
    actual=trip['confirmed_trip']['total_carbon_kg'];saved,amount=journey_points(q['expected_kg'],actual,q['policy'])
    return persist(data,{'id':rid,'kind':'trip','user_id':user['user_id'],'campaign_id':user['campaign_id'],'trip_id':trip['trip_id'],
        'title':'출퇴근 탄소 절감 보상','status':'paid' if amount>0 else 'no_reduction','points':amount,
        'saved_kg':saved,'baseline_kg':q['expected_kg'],'actual_kg':actual,'source':q['source'],'development_only':q['development_only'],
        'model_version':q['model_version'],'policy_version':q['policy']['version'],'created_at':datetime.now(timezone.utc).isoformat()})
