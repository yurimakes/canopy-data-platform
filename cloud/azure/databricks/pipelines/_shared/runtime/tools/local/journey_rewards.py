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
    return {**route,'id':quote['id'],'quoteId':quote['id'],'expectedKg':quote['expected_kg'],'baselineSource':quote['source'],'modeProbabilities':quote.get('probabilities',{}),
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
        'route':route,'direction':direction,'development_only':__import__('services.domain_context',fromlist=['backend']).backend.get() is None,'policy':extension_policy(),
        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    store(data).create_item(quote)
    return {**route,'id':quote['id'],'quoteId':quote['id'],'expectedKg':quote['expected_kg'],'baselineSource':quote['source'],'modeProbabilities':quote.get('probabilities',{}),
        'provider':'local-test','searchedAt':datetime.now(timezone.utc).isoformat(),'fare':None}


def prepare(data,user,quote_id,direction="outbound"):
    if direction not in ("outbound","return"):raise ApiError(400,"invalid_direction","출근 또는 퇴근을 선택해주세요.")
    s=store(data);key=identity('intent',user,'next')
    quote=None
    if quote_id:
        try:quote=s.read_item(quote_id)
        except CosmosResourceNotFoundError:raise ApiError(404,'quote_not_found','저장된 경로가 없습니다. 다시 선택해주세요.')
        if quote['user_id']!=user['user_id'] or quote['campaign_id']!=user['campaign_id']:raise ApiError(403,'forbidden','다른 사용자의 경로')
        if datetime.fromisoformat(quote['expires_at'])<datetime.now(timezone.utc):raise ApiError(409,'expired','경로 기준을 다시 확인해주세요.')
    item={'id':key,'quote':quote,'direction':quote.get('direction',direction) if quote else direction}
    try:s.create_item(item)
    except CosmosResourceExistsError:
        old=s.read_item(key);s.replace_item(key,item,etag=old['_etag'])


def bind(data,user,trip_id):
    from reward_baselines import freeze
    context=freeze(data,user,user.get("started_at"))
    s=store(data)
    try:intent=s.read_item(identity('intent',user,'next'))
    except CosmosResourceNotFoundError:intent={'quote':None}
    if intent['quote'] and datetime.fromisoformat(intent['quote']['expires_at'])<datetime.now(timezone.utc):
        raise ApiError(409,'expired','경로 기준을 다시 확인해주세요.')
    try:s.create_item({'id':'trip:'+trip_id,'quote':intent['quote'],'context':context})
    except CosmosResourceExistsError:pass


def start_trip(data,user,body,api):
    """Validate first, then atomically create a Trip with its immutable context."""
    import json
    from services.trip_service import NAMESPACE,required
    if not user.get('campaign_id') or user.get('campaign_left_at'):
        raise ApiError(403,'campaign_required','참여 중인 캠페인이 필요합니다.')
    if body.get('campaign_id',user['campaign_id'])!=user['campaign_id']:
        raise ApiError(403,'campaign_mismatch','가입한 캠페인으로만 여정을 시작할 수 있습니다.')
    request=required(body,'request_id');required(body,'device_id')
    tid=str(uuid.uuid5(NAMESPACE,json.dumps([user['user_id'],request])))
    # A response-lost retry must return the original Trip even after quote expiry.
    if api.store.read(tid,user['user_id']):return api.start(user['user_id'],body,campaign_id=user['campaign_id'])
    try:intent=store(data).read_item(identity('intent',user,'next'))
    except CosmosResourceNotFoundError:intent={'quote':None,'direction':'outbound'}
    q=intent.get('quote')
    if q and datetime.fromisoformat(q['expires_at'])<datetime.now(timezone.utc):
        raise ApiError(409,'expired','경로 기준이 만료됐어요. 출발 전 기준을 다시 확인해주세요.')
    from reward_baselines import freeze
    context={'quote':q,'direction':intent.get('direction','outbound'),'home':user.get('home'),'work':user.get('work'),
             'context':freeze(data,user,api.clock())}
    return api.start(user['user_id'],body,campaign_id=user['campaign_id'],start_context=context)


def settle(data,user,trip,points):
    from reward_baselines import freeze,week_of
    from math import isfinite
    # Ownership must be checked even on idempotent retries.
    if any(trip.get(k)!=user.get(k) for k in ('user_id','campaign_id')):raise ApiError(404,'not_found','여정 없음')
    if trip.get('is_mock') or (trip.get('confirmed_trip') or {}).get('is_mock') or (trip.get('start_context') or {}).get('simulation'):return {'status':'test_trip','message':'테스트 여정은 실제 보상·미션·랭킹에 포함되지 않습니다.'}
    rid=identity('trip',user,trip['trip_id']);old=existing(data,rid)
    if old:return old
    if trip['status']!='ready':return {'status':'processing'}
    if (trip.get('data_quality') or {}).get('status')=='partial':
        return {'status':'insufficient_gps','message':'위치 수집 공백 또는 정확도 문제로 전체 이동을 확인할 수 없어 보상을 계산하지 않았어요.'}
    # Preserve old weekly payouts; do not back-pay Trips already covered by them.
    from business import LedgerStore
    for previous in LedgerStore(Path(data)/'rewards.sqlite').all():
        if previous.get('user_id')==user['user_id'] and previous.get('campaign_id')==user['campaign_id'] and previous.get('status')=='paid' and (previous.get('week_label') or previous.get('week'))==week_of(trip['started_at']):
            cutoff=previous.get('occurred_at')
            if not cutoff or datetime.fromisoformat(trip['ended_at'].replace('Z','+00:00'))<=datetime.fromisoformat(cutoff.replace('Z','+00:00')):
                return {'status':'legacy_weekly_paid','message':'이 여정은 기존 주간 지급에 포함되어 중복 지급하지 않습니다.'}

    try:bound=store(data).read_item('trip:'+trip['trip_id'])
    except CosmosResourceNotFoundError:bound={}
    bound=trip.get('start_context') or bound
    q=bound.get('quote');context=bound.get('context') or freeze(data,user,trip['started_at'])
    if q and (q['user_id']!=user['user_id'] or q['campaign_id']!=user['campaign_id']):raise ApiError(403,'forbidden','다른 사용자의 여정')
    def stamp(v):return datetime.fromisoformat(v.replace('Z','+00:00'))
    valid=sorted([p for p in points if stamp(trip['started_at'])-timedelta(seconds=1)<=stamp(p['event_time'])<=stamp(trip['ended_at'])+timedelta(seconds=1)],key=lambda p:stamp(p['event_time']))
    confirmed=trip.get('confirmed_trip') or {}
    meters=confirmed.get('total_distance_m')
    actual=confirmed.get('total_carbon_kg')
    if not isinstance(meters,(int,float)) or isinstance(meters,bool) or not isfinite(meters) or meters<=0 or not isinstance(actual,(int,float)) or isinstance(actual,bool) or not isfinite(actual) or actual<0:
        return {'status':'invalid_trip','message':'유효한 확정 거리와 탄소 결과가 필요합니다.'}
    personal=context['personal'];global_value=context['global'] if personal is not None else None
    actual_rate=actual*1000000/meters
    selected=None;classification='no_change'
    if personal is not None and actual_rate<personal:selected=personal;classification='improved'
    elif global_value is not None and actual_rate<=global_value:selected=global_value;classification='maintained'
    elif personal is not None or global_value is not None:selected=personal if personal is not None else global_value
    source='Global · 해당 주 고정 참여자 기준' if classification=='maintained' else 'Personal · 해당 주 고정 개인 기준'
    model_version=None
    if selected is None:
        if q:
            if len(valid)<2:return {'status':'insufficient_gps','message':'출발·도착 GPS가 부족합니다.'}
            def point(p):return {'lat':p['latitude'],'lon':p['longitude']}
            radius=q['policy']['endpoint_radius_m']
            if distance(valid[0],point(q['route']['from']))>radius or distance(valid[-1],point(q['route']['to']))>radius:
                # A route quote is not transferable to a different journey.
                q=None
        # Population remains route-dependent; use the Trip's actual distance with its KTDB rate.
        if not q:
            if len(valid)<2:return {'status':'insufficient_gps','message':'KTDB 기준 산정에 필요한 출발·도착 GPS가 부족합니다.'}
            def endpoint(p):return {'latitude':p['lat'],'longitude':p['lon']}
            from population import estimate
            route={'from':endpoint(valid[0]),'to':endpoint(valid[-1]),'distance_m':meters}
            try:population=estimate(route,direction=bound.get('direction','outbound'),at=stamp(trip['started_at']))
            except (OSError,ValueError,ImportError) as exc:
                return {'status':'awaiting_baseline','message':'KTDB 기준을 불러오지 못했습니다. 다시 확인해주세요.'}
            q={**population,'route':route,'development_only':True}
        selected=q['expected_kg']*1000000/float(q['route']['distance_m'])
        source=q['source'];model_version=q['model_version'];classification='population'
    reference=selected*meters/1000000
    policy=context['policy'];saved,amount=journey_points(reference,actual,policy)
    return persist(data,{'id':rid,'kind':'trip','user_id':user['user_id'],'campaign_id':user['campaign_id'],'trip_id':trip['trip_id'],
        'title':'여정 탄소 유지 보상' if classification=='maintained' else '여정 탄소 절감 보상','status':'paid' if amount>0 else 'no_reduction','points':amount,
        'week':context['week'],'baseline_week':context['week'],'baseline_snapshot_id':context['id'],'classification':classification,
        'personal_g_per_km':personal,'global_g_per_km':global_value,'baseline_g_per_km':selected,'distance_m':meters,
        'saved_kg':saved,'baseline_kg':reference,'actual_kg':actual,'source':source,'development_only':__import__('services.domain_context',fromlist=['backend']).backend.get() is None,
        'model_version':model_version,'settlement_version':'local-trip-settlement-v2','policy_version':policy['version'],'baseline_policy':context,
        'created_at':datetime.now(timezone.utc).isoformat()})
