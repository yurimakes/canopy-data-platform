import copy
import pytest
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from services.weekly_cosmos import publish,WeeklyReader,CONTROL
from services.feature_documents import FeatureDocuments
class Container:
 def __init__(self,key):self.key=key;self.rows={};self.fail=False
 def upsert_item(self,b):
  if self.fail:raise RuntimeError('write failure')
  v=copy.deepcopy(b);v['_etag']='1';self.rows[(v[self.key],v['id'])]=v;return v
 def read_item(self,i,partition_key):
  if (partition_key,i) not in self.rows:raise CosmosResourceNotFoundError(status_code=404)
  return copy.deepcopy(self.rows[(partition_key,i)])
 def create_item(self,b):return self.upsert_item(b)
 def replace_item(self,i,b,**kwargs):return self.upsert_item(b)
 def query_items(self,query,parameters,**kwargs):
  p={x['name']:x['value'] for x in parameters};rows=list(self.rows.values())
  if '@g' in p:rows=[r for r in rows if r.get('generation')==p['@g'] and r.get('artifact')==p['@a'] and r.get('audience') in (p['@campaign'],p['@all'])];return sorted(rows,key=lambda r:r['ordinal'])
  return [r for r in rows if r.get('scope')==p['@scope'] and ('@id' not in p or r['id']==p['@id'])]
class DB:
 def __init__(self):self.c={n:Container(k) for n,k in {'baseline_metrics':'campaign_id','ranking':'campaign_id','mission-state':'pk','rewards':'user_id','missions':'user_id','mission_events':'user_id'}.items()}
 def get_container_client(self,n):return self.c[n]
def test_publication_does_not_expose_partial_or_cross_campaign():
 db=DB();pointer={'generation':'a'*32,'completed_at':'2026-09-20T00:00:00+00:00'}
 assert publish(db,pointer,{'ranking':[{'campaign_id':'a','score':1},{'campaign_id':'b','score':2}],'run':{'status':'ok'}})=='published'
 assert WeeklyReader(db).read('ranking','a')==[{'campaign_id':'a','score':1}]
 assert WeeklyReader(db).read('run','a')=={'status':'ok'}
 db.c['ranking'].fail=True
 with pytest.raises(RuntimeError):publish(db,{'generation':'b'*32,'completed_at':'2026-09-21T00:00:00+00:00'},{'ranking':[{'campaign_id':'a','score':99}]})
 assert WeeklyReader(db).read('ranking','a')[0]['score']==1
 assert publish(db,pointer,{})=='already_published'
def test_feature_partition_contract_and_campaign_isolation():
 db=DB();a=FeatureDocuments(db,'a','bonus-rewards');b=FeatureDocuments(db,'b','bonus-rewards')
 a.create_item({'id':'r','user_id':'u','points':3})
 assert ('u','r') in db.c['rewards'].rows
 assert a.read_item('r')['points']==3
 with pytest.raises(CosmosResourceNotFoundError):b.read_item('r')
 assert b.all()==[]


def test_missing_numeric_baseline_publishes_null_but_infinity_keeps_old_snapshot():
 import json
 db=DB();pointer={'generation':'c'*32,'completed_at':'2026-09-20T00:00:00+00:00'}
 publish(db,pointer,{'effective_personal_baseline':[{'campaign_id':'a','status':'collecting','baseline_g_co2e_per_km':float('nan'),'nested':[float('nan')]}]})
 rows=WeeklyReader(db).read('effective_personal_baseline','a')
 assert rows[0]['baseline_g_co2e_per_km'] is None and rows[0]['nested']==[None]
 json.dumps(rows,allow_nan=False)
 with pytest.raises(ValueError,match='Infinite'):
  publish(db,{'generation':'d'*32,'completed_at':'2026-09-21T00:00:00+00:00'},{'ranking':[{'campaign_id':'a','points':float('inf')}]})
 assert WeeklyReader(db).control('weekly:current')['generation']==pointer['generation']
