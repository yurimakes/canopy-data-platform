"""Feature containers matching the original Cosmos partition contract."""
import hashlib,json
from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosResourceNotFoundError
FEATURES={
 'bonus-rewards':('rewards','user_id'),'rewards':('rewards','user_id'),
 'missions':('missions','user_id'),'mission-events':('mission_events','user_id'),
 'journey-quotes':('baseline_metrics','campaign_id'),'reward-baselines':('baseline_metrics','campaign_id'),
}
CONTAINERS={'rewards':'user_id','ranking':'campaign_id','baseline_metrics':'campaign_id','missions':'user_id','mission_events':'user_id','mission-state':'pk'}
def destination(namespace):return FEATURES.get(namespace,('mission-state','pk'))
class FeatureDocuments:
 def __init__(self,database,campaign,namespace):
  name,self.key=destination(namespace);self.container=database.get_container_client(name)
  self.campaign=campaign;self.namespace=namespace
  self.scope=hashlib.sha256(json.dumps([campaign,namespace]).encode()).hexdigest()
 def record(self,body):
  payload={k:v for k,v in body.items() if not k.startswith('_')}
  pk=payload.get(self.key) if self.key=='user_id' else self.campaign if self.key=='campaign_id' else self.scope
  if not pk:raise ValueError('Missing feature partition: '+self.namespace)
  return {**payload,'id':body['id'],self.key:pk,'campaign_id':self.campaign,'scope':self.scope,'namespace':self.namespace,'payload':payload}
 def find(self,item):
  rows=list(self.container.query_items(query='SELECT * FROM c WHERE c.id=@id AND c.scope=@scope',parameters=[{'name':'@id','value':item},{'name':'@scope','value':self.scope}],enable_cross_partition_query=True))
  if not rows:raise CosmosResourceNotFoundError(status_code=404,message='not found')
  if len(rows)!=1:raise RuntimeError('Ambiguous feature document')
  return rows[0]
 def read_item(self,item,partition_key=None):
  r=self.find(item);body={**r['payload'],'_etag':r['_etag']}
  if partition_key is not None and body.get('user_id')!=partition_key:raise CosmosResourceNotFoundError(status_code=404,message='partition mismatch')
  return body
 def create_item(self,body):
  r=self.container.create_item(self.record(body));return {**r['payload'],'_etag':r['_etag']}
 def replace_item(self,item,body,etag=None,match_condition=None):
  r=self.container.replace_item(item,self.record(body),etag=etag,match_condition=MatchConditions.IfNotModified);return {**r['payload'],'_etag':r['_etag']}
 def all(self):
  return [r['payload'] for r in self.container.query_items(query='SELECT c.payload FROM c WHERE c.scope=@scope',parameters=[{'name':'@scope','value':self.scope}],enable_cross_partition_query=True)]
