"""팀 Mission/Reward 계산을 로컬 저장소와 연결. 정책 계산 재작성 제외."""
import json
import sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT/'cloud/azure/functions/func_canopy_dev'),str(ROOT/'cloud/azure/pipelines/databricks')]
from services.local_documents import LocalDocuments
from azure.cosmos.exceptions import CosmosResourceNotFoundError,CosmosResourceExistsError
from mission_engine import get_week_state,load_mission_policy,bundle_id
from services.mission_progress import build_progress_rows
from services.mission_response import build_response_rows


def read_rows(path):
    from services.domain_context import backend,read_json
    if backend.get() is not None:return read_json(path,[])
    from weekly_publication import resolve
    path=resolve(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


class MissionRepo:
    def __init__(self,data,profiles=None,persist=True,week=None):
        self.data=Path(data)
        self.store=LocalDocuments(self.data/'missions.sqlite')
        self.profiles=profiles
        self.persist=persist
        self.preview={}
        self.week=week or str(datetime.now(ZoneInfo('Asia/Seoul')).date())
    def pk(self,campaign,user):return campaign+':'+user
    def get_bundle(self,campaign,user,week):
        if not self.persist:return self.preview.get(bundle_id(campaign,user,week))
        try:return self.store.read_item(bundle_id(campaign,user,week))
        except CosmosResourceNotFoundError:return None
    def get_latest_profile(self,campaign,user):
        records=self.profiles if self.profiles is not None else read_rows(self.data/'weekly/weekly_user_profile.json')
        records=[r for r in records if r['campaign_id']==campaign and r['user_id']==user and r.get('effective_week_start',self.week)<=self.week]
        if not records:return None
        result=dict(max(records,key=lambda r:r['source_week_start']))
        for key in ('category_preferences','difficulty_state','family_capability'):
            if key+'_json' in result:result[key]=json.loads(result[key+'_json'])
        return result
    def create_bundle(self,item):
        if not self.persist:
            self.preview[item['id']]=item
            return item
        try:return self.store.create_item(item)
        except CosmosResourceExistsError:return self.store.read_item(item['id'])


def issue(data,user,week=None,profiles=None,persist=True):
    day=week or datetime.now(ZoneInfo('Asia/Seoul')).date()
    start=day-timedelta(days=day.weekday());end=start+timedelta(days=7)
    repo=MissionRepo(data,profiles,persist,str(start))
    policy=load_mission_policy(ROOT/'cloud/azure/functions/func_canopy_dev/mission_policy.yaml')
    get_week_state(repo,policy,user_id=user['user_id'],campaign_id=user['campaign_id'],week_start=str(start),week_end=str(end),now_iso=datetime.now(timezone.utc).isoformat())
    return repo.get_bundle(user['campaign_id'],user['user_id'],str(start))


def mission_history(data,trips,bundles=None,events=None):
    bundles=bundles if bundles is not None else MissionRepo(data).store.all()
    progress=build_progress_rows(bundles,trips,campaign_timezone='Asia/Seoul',as_of_iso=datetime.now(timezone.utc).isoformat())
    return bundles,progress,build_response_rows(bundles,progress,LocalDocuments(Path(data)/'mission-events.sqlite').all() if events is None else events)


def current_missions(data,user,trips):
    bundle=issue(data,user)
    _,progress,_=mission_history(data,trips,[bundle])
    by_id={p['assignment_id']:p for p in progress}
    result=dict(bundle)
    result['missions']=[{**m,**by_id.get(m['assignment_id'],{})} for m in bundle['missions']]
    return result


def owned_missions(data,user,trips):
    """Recompute owned historical assignments so unclaimed rewards survive rollover."""
    issue(data,user)
    bundles=[b for b in MissionRepo(data).store.all() if b['user_id']==user['user_id'] and b['campaign_id']==user['campaign_id']]
    _,progress,_=mission_history(data,trips,bundles)
    by_id={p['assignment_id']:p for p in progress}
    return [{**b,'missions':[{**m,**by_id.get(m['assignment_id'],{}),'week_start':b['week_start']} for m in b['missions']]} for b in sorted(bundles,key=lambda b:b['week_start'],reverse=True)]


def visible_missions(bundles,at=None):
    """Upcoming assignments never replace this week's active assignments."""
    day=(at or datetime.now(ZoneInfo('Asia/Seoul'))).astimezone(ZoneInfo('Asia/Seoul')).date()
    week=str(day-timedelta(days=day.weekday()))
    current=next((b for b in bundles if b['week_start']==week),None)
    if current is None:
        current={'week_start':week,'missions':[]}
    return {**current,'missions':[m for b in bundles for m in b['missions']
        if b['week_start']==week or (b['week_start']<week and m.get('completed'))]}


def record_mission_event(data,user,body):
    from services.trip_service import ApiError
    from rewards import identity
    assignment=body.get('assignment_id');kind=body.get('event_type');event=body.get('event_id')
    if kind not in ('shown','started') or not isinstance(event,str) or not 1<=len(event)<=100:
        raise ApiError(400,'invalid_event','미션 이벤트 형식을 확인해주세요.')
    owned=any(b['user_id']==user['user_id'] and b['campaign_id']==user['campaign_id'] and any(m['assignment_id']==assignment for m in b['missions']) for b in MissionRepo(data).store.all())
    if not owned:raise ApiError(404,'mission_not_found','내 미션이 아닙니다.')
    row={'id':identity('mission-event',user,event),'event_id':identity('mission-event',user,event),'assignment_id':assignment,
         'event_type':kind,'user_id':user['user_id'],'campaign_id':user['campaign_id'],'occurred_at':datetime.now(timezone.utc).isoformat()}
    db=LocalDocuments(Path(data)/'mission-events.sqlite')
    try:db.create_item(row)
    except CosmosResourceExistsError:pass
    return {'status':'accepted'}


class LedgerStore(LocalDocuments):
    def read_item(self,item,partition_key=None):
        value=super().read_item(item)
        if partition_key is not None and value['user_id']!=partition_key:raise CosmosResourceNotFoundError(status_code=404,message='partition mismatch')
        return value


def publish_rewards(data,rows):
    from reward_ledger import process_reward_batch
    store=LedgerStore(Path(data)/'rewards.sqlite')
    process_reward_batch(store,rows)
    return store.all()


def weekly_outputs(results):
    def key(r):return r.get('campaign_id'),r.get('user_id'),r.get('week')
    baseline={key(r):r for r in results['baseline_gold']}
    profiles={(r['campaign_id'],r['user_id'],r['source_week_start']):r for r in results['weekly_user_profile']}
    missions={(r['campaign_id'],r['user_id'],r['week_start']):r for r in results['next_week_missions']}
    kpis={(r['campaign_id'],r['week']):r for r in results['campaign_kpi']}
    output=[]
    for row in results['weekly_gold']:
        start=datetime.strptime(row['week']+'-1','%G-W%V-%u').date()
        output.append({'campaign_id':row['campaign_id'],'user_id':row['user_id'],'week':row['week'],
            'weekly':row,'baseline':baseline.get(key(row)),
            'profile':profiles.get((row['campaign_id'],row['user_id'],str(start))),
            'missions':missions.get((row['campaign_id'],row['user_id'],str(start+timedelta(days=7)))),
            'ranking':[r for r in results['ranking'] if r['campaign_id']==row['campaign_id'] and r['week']==row['week'] and r.get('user_id')==row['user_id']],
            'campaign_kpi':kpis.get((row['campaign_id'],row['week']))})
    return output
