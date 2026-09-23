"""Immutable per-row weekly projections; atomically publish after readback validation."""
import hashlib,json,math
from datetime import datetime
from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosResourceNotFoundError
CONTROL='__weekly_publication__'
def json_value(value):
 """Pandas uses NaN for absent numeric cells; JSON/Cosmos require explicit null."""
 if isinstance(value,float):
  if math.isnan(value):return None
  if not math.isfinite(value):raise ValueError('Infinite weekly numeric value')
 if isinstance(value,dict):return {k:json_value(v) for k,v in value.items()}
 if isinstance(value,list):return [json_value(v) for v in value]
 return value
def container_for(name):
 if name in ('ranking','reward_calculation','reward_ledger'):return 'ranking'
 if name in ('weekly_user_profile','next_week_missions','mission_progress','mission_response_weekly'):return 'mission-state'
 return 'baseline_metrics'
def partition(name):return 'pk' if container_for(name)=='mission-state' else 'campaign_id'
class WeeklyReader:
 def __init__(self,database):self.db=database;self.pointer=None
 def control(self,name,default=None):
  try:return self.db.get_container_client('baseline_metrics').read_item(name,partition_key=CONTROL)['payload']
  except CosmosResourceNotFoundError:return default
 def read(self,name,campaign,default=None):
  if name=='last-attempt':return self.control(name,default)
  if self.pointer is None:self.pointer=self.control('weekly:current',{})
  generation=self.pointer.get('generation')
  if not generation:return default
  descriptor=self.pointer['artifacts'].get(name)
  if descriptor is None:return default
  target=self.db.get_container_client(container_for(name))
  rows=list(target.query_items(query='SELECT c.ordinal,c.payload FROM c WHERE c.generation=@g AND c.artifact=@a AND (c.audience=@campaign OR c.audience=@all) ORDER BY c.ordinal',parameters=[{'name':'@g','value':generation},{'name':'@a','value':name},{'name':'@campaign','value':campaign},{'name':'@all','value':'__all__'}],enable_cross_partition_query=True))
  if not descriptor['list']:return rows[0]['payload'] if rows else default
  return [r['payload'] for r in rows]
def publish(database,pointer,outputs):
 outputs=json_value(outputs)
 json.dumps(outputs,allow_nan=False)
 control=database.get_container_client('baseline_metrics')
 try:old=control.read_item('weekly:current',partition_key=CONTROL)
 except CosmosResourceNotFoundError:old=None
 if old and old['payload'].get('generation')==pointer['generation']:return 'already_published'
 if old and datetime.fromisoformat(old['payload']['completed_at'])>=datetime.fromisoformat(pointer['completed_at']):raise ValueError('Stale weekly publication')
 artifacts={}
 for name,value in outputs.items():
  target=database.get_container_client(container_for(name));key=partition(name)
  rows=value if isinstance(value,list) else [value]
  artifacts[name]={'list':isinstance(value,list),'count':len(rows)}
  for i,row in enumerate(rows):
   audience=row.get('campaign_id') or '__all__';ident=pointer['generation']+':'+name+':'+str(i)
   body={'id':ident,key:audience,'audience':audience,'generation':pointer['generation'],'artifact':name,'ordinal':i,'payload':row}
   target.upsert_item(body)
   if target.read_item(ident,partition_key=audience)['payload']!=row:raise ValueError('Cosmos projection readback mismatch')
 body={'id':'weekly:current','campaign_id':CONTROL,'payload':{**pointer,'artifacts':artifacts}}
 if old:control.replace_item(body['id'],body,etag=old['_etag'],match_condition=MatchConditions.IfNotModified)
 else:control.create_item(body)
 return 'published'
