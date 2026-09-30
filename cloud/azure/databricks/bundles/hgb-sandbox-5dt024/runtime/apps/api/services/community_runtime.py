"""Hosted adapters for the same domain used by tools/local/server.py."""
import hashlib
import json
import os
import sys
from pathlib import Path
from .domain_context import use_backend
from .trip_service import ApiError

def domain_root():
    root=next((p for p in Path(__file__).resolve().parents if (p/'tools/local').exists()),None)
    if root is None:raise RuntimeError('shared community domain missing from package')
    path=str(root/'tools/local')
    if path not in sys.path:sys.path.insert(0,path)
    assets=root/'runtime-assets'
    if assets.exists():
        os.environ.setdefault('CANOPY_KTDB_REFERENCE_ROOT',str(assets/'reference-model'))
        os.environ.setdefault('CANOPY_KTDB_MODEL_PATH',str(assets/'models/ktdb_population_baseline.pkl'))
    return root

class CosmosDocuments:
    def __init__(self,container,campaign,namespace):
        self.container=container
        self.scope=hashlib.sha256(json.dumps([campaign,namespace]).encode()).hexdigest()
    def read_item(self,item,partition_key=None):
        result=self.container.read_item(item,partition_key=self.scope)
        body={**result['payload'],'_etag':result['_etag']}
        if partition_key is not None and body.get('user_id')!=partition_key:
            from azure.cosmos.exceptions import CosmosResourceNotFoundError
            raise CosmosResourceNotFoundError(status_code=404,message='partition mismatch')
        return body
    def create_item(self,body):
        result=self.container.create_item({'id':body['id'],'scope':self.scope,'payload':body})
        return {**body,'_etag':result['_etag']}
    def replace_item(self,item,body,etag=None,match_condition=None):
        from azure.core import MatchConditions
        result=self.container.replace_item(item,{'id':item,'scope':self.scope,'payload':body},etag=etag,match_condition=MatchConditions.IfNotModified)
        return {**body,'_etag':result['_etag']}
    def all(self):
        return [r['payload'] for r in self.container.query_items(query='SELECT c.payload FROM c WHERE c.scope=@scope',
            parameters=[{'name':'@scope','value':self.scope}],partition_key=self.scope)]

class HostedBackend:
    def __init__(self,user,trip_api,container,users,blob,database=None):
        self.user=user;self.api=trip_api;self.container=container;self.users=users;self.blob=blob;self.cache={};self.database=database
    def documents(self,name):
        if self.database is not None:
            from .feature_documents import FeatureDocuments
            return FeatureDocuments(self.database,self.user['campaign_id'],name)
        return CosmosDocuments(self.container,self.user['campaign_id'],name)
    def read_json(self,path,default=None):
        path=Path(path);name=path.name
        if path.parent.name=='inputs':
            if name=='trips.json':return self.api.store.for_user(self.user['user_id'])
            if name=='users.json':return list(self.users.query_items(query='SELECT c.user_id,c.campaign_id,c.nickname,c.department_id,c.department_name FROM c WHERE c.campaign_id=@campaign',parameters=[{'name':'@campaign','value':self.user['campaign_id']}],enable_cross_partition_query=True))
            if name=='reward_ledger_history.json':return self.documents('rewards').all()
            return default
        if path.parent.name=='weekly':
            if self.database is not None:
                from .weekly_cosmos import WeeklyReader
                if 'cosmos_weekly' not in self.cache:self.cache['cosmos_weekly']=WeeklyReader(self.database)
                return self.cache['cosmos_weekly'].read(path.stem,self.user['campaign_id'],default)
            if 'pointer' not in self.cache:
                self.cache['pointer']=self.download('weekly/current.json',{})
            pointer=self.cache['pointer']
            if name=='last-attempt.json':return self.download('weekly/last-attempt.json',default)
            generation=pointer.get('generation')
            if not generation:return default
            if len(generation)!=32 or any(c not in '0123456789abcdef' for c in generation):raise ValueError('invalid publication')
            key='weekly/generations/'+generation+'/'+name
            if key not in self.cache:self.cache[key]=self.download(key,default)
            value=self.cache[key]
            if isinstance(value,list):return [r for r in value if r.get('campaign_id') in (None,self.user['campaign_id'])]
            return value
        return default
    def download(self,name,default):
        from azure.core.exceptions import ResourceNotFoundError
        try:return json.loads(self.blob.download_blob(name).readall())
        except ResourceNotFoundError:return default
    def estimate(self,route,direction,at):
        from population import estimate
        with use_backend(None):return estimate(route,direction,at)

def hosted(user,api):
    domain_root()
    from .runtime import user_registration
    from azure.storage.blob import BlobServiceClient
    from azure.identity import DefaultAzureCredential
    if os.getenv('CANOPY_FEATURE_CONTAINERS')=='true':
        database=api.store.client.get_database_client(os.environ['COSMOS_TRIPS_DATABASE'])
        return HostedBackend(user,api,None,user_registration().container,None,database=database)
    required=('CANOPY_APP_STATE_CONTAINER','CANOPY_WEEKLY_STORAGE_URL','CANOPY_WEEKLY_CONTAINER')
    if any(not os.getenv(k) for k in required):raise ApiError(503,'community_not_configured','서비스 저장소 설정을 확인해주세요.')
    container=api.store.client.get_database_client(os.environ['COSMOS_TRIPS_DATABASE']).get_container_client(os.environ['CANOPY_APP_STATE_CONTAINER'])
    if container.read()['partitionKey']['paths']!=['/scope']:raise RuntimeError('app state partition key must be /scope')
    blob=BlobServiceClient(os.environ['CANOPY_WEEKLY_STORAGE_URL'],credential=DefaultAzureCredential()).get_container_client(os.environ['CANOPY_WEEKLY_CONTAINER'])
    return HostedBackend(user,api,container,user_registration().container,blob)

def dispatch_domain(method,path,body,user,api,provider=None):
    domain_root()
    provider=provider or hosted(user,api)
    data=Path('/canopy-domain')
    with use_backend(provider):
        if path=='/api/trips/start' and method=='POST':
            from journey_rewards import start_trip
            from .trip_service import public
            result,created=start_trip(data,user,body,api)
            return (201 if created else 200),public(result)
        if path in ('/api/community','/api/notifications/read'):
            from community_service import view
            result=view(data,user,api.store.for_user(user['user_id']))
            if path.endswith('/read'):
                from activity import mark_read
                return 200,mark_read(data,user,body.get('id'),{r['id'] for r in result['notifications']['data']['items']})
            return 200,result
        if path=='/api/journey/prepare' and method=='POST':
            from journey_rewards import prepare
            prepare(data,user,body.get('quote_id'),body.get('direction','outbound'))
            return 200,{'status':'prepared'}
        if path=='/api/journey/quote' and method=='POST':
            from journey_rewards import route_quote
            if not isinstance(body.get('from'),dict) or not isinstance(body.get('to'),dict):raise ApiError(400,'invalid_route','출발지와 도착지가 필요합니다.')
            return 200,route_quote(data,user,body['from'],body['to'],body.get('direction','outbound'))
        if path=='/api/missions/events' and method=='POST':
            from business import record_mission_event
            return 200,record_mission_event(data,user,body)
        if path=='/api/missions/acknowledge' and method=='POST':
            from rewards import acknowledge_mission
            if not isinstance(body.get('assignment_id'),str):raise ApiError(400,'invalid_assignment','미션 식별자가 필요합니다.')
            return 200,acknowledge_mission(data,user,body['assignment_id'],api.store.for_user(user['user_id']))
        if path.startswith('/api/comparison/') and method=='GET':
            from journey_rewards import settle
            trip=api.get(path.rsplit('/',1)[-1],user['user_id'])
            return 200,settle(data,user,trip,trip.get('endpoint_observations') or [])
    raise ApiError(404,'not_found','요청한 기능을 찾을 수 없습니다.')


def recover_settlements(api,limit=50):
    """Durable ready-Trip scan; payment is not dependent on opening a screen."""
    from datetime import datetime,timezone,timedelta
    from .cosmos_service import Conflict
    domain_root()
    now=datetime.now(timezone.utc)
    rows=api.store.container.query_items(query=f"SELECT TOP {int(limit)} * FROM c WHERE c.type='trip' AND c.status='ready' "
        "AND (NOT IS_DEFINED(c.reward_settlement_terminal) OR c.reward_settlement_terminal=false) "
        "AND (NOT IS_DEFINED(c.reward_retry_at) OR c.reward_retry_at<=@now)",parameters=[{'name':'@now','value':now.isoformat()}],enable_cross_partition_query=True)
    for trip in rows:
        try:
            _,result=dispatch_domain('GET','/api/comparison/'+trip['trip_id'],{},trip,api)
            terminal=result.get('status') not in ('processing','awaiting_baseline','retrying')
            trip.update(reward_settlement_terminal=terminal,reward_retry_at=(now+timedelta(minutes=5)).isoformat(),reward_settlement_status=result.get('status'))
            api.store.replace(trip)
        except Conflict:continue
        except Exception:
            import logging
            logging.error('trip_reward_recovery_failed')
            try:
                trip.update(reward_retry_at=(now+timedelta(minutes=5)).isoformat())
                api.store.replace(trip)
            except Conflict:pass
