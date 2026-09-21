"""Run hosted dispatch against an isolated durable adapter; never contact Azure."""
from pathlib import Path
from types import SimpleNamespace
from services.domain_context import use_backend
from services.local_documents import LocalDocuments
from services.community_runtime import dispatch_domain,CosmosDocuments
from services.cosmos_service import SQLiteTripStore
from services.trip_service import TripService
from services.mock_trip_processor import MockTripProcessor
from test_rewards import USER,prepared

class Proxy:
    def __init__(self,value):self.value=value
    def __getattr__(self,name):return getattr(self.value,name)

class Backend:
    def __init__(self,path):self.path=path
    def documents(self,name):
        with use_backend(None):return Proxy(LocalDocuments(self.path/(name+'.sqlite')))
    def read_json(self,path,default=None):
        import json
        p=self.path/Path(path).parent.name/Path(path).name
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def test_hosted_dispatch_uses_same_reward_and_mission_domain(tmp_path):
    from journey_rewards import settle
    trip,points=prepared(tmp_path)
    trip.update(id=trip['trip_id'],type='trip',endpoint_observations=points)
    api=TripService(SQLiteTripStore(str(tmp_path/'trips.sqlite')),MockTripProcessor())
    api.store.create(trip)
    provider=Backend(tmp_path)
    status,result=dispatch_domain('GET','/api/comparison/trip',{},USER,api,provider)
    assert status==200 and result['points']==30
    assert settle(tmp_path,USER,trip,points)['id']==result['id']
    _,panel=dispatch_domain('GET','/api/community',{},USER,api,provider)
    assert panel['rewards']['data']['balance']==30
    assert len(panel['missions']['data']['items'])==4
    _,again=dispatch_domain('GET','/api/comparison/trip',{},USER,api,provider)
    assert again['id']==result['id']

def test_cosmos_namespace_and_campaign_are_separate():
    a=CosmosDocuments(None,'campaign-a','rewards')
    b=CosmosDocuments(None,'campaign-b','rewards')
    c=CosmosDocuments(None,'campaign-a','missions')
    assert len({a.scope,b.scope,c.scope})==3
