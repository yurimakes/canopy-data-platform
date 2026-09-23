"""Isolated Azure acceptance test of the unmodified managed weekly entry point."""
import argparse,inspect,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(inspect.currentframe().f_code.co_filename).resolve().parents[4]
for d in (ROOT/'apps/api',ROOT/'tools/local',ROOT/'cloud/azure/pipelines/weekly_analysis',ROOT/'cloud/azure/pipelines/databricks'):sys.path.insert(0,str(d))
def main():
 p=argparse.ArgumentParser();p.add_argument('--fixture',required=True);a=p.parse_args();f=json.loads(Path(a.fixture).read_text())
 assert f['prefix'].startswith('qaweekly_') and f['schema'].split('.')[1].startswith('qaweekly_')
 from azure.cosmos import CosmosClient,PartitionKey
 from databricks.sdk.runtime import dbutils
 from pyspark.sql import SparkSession
 from services.feature_documents import FeatureDocuments,CONTAINERS
 from services.weekly_cosmos import WeeklyReader,CONTROL
 import weekly_managed_job
 real=CosmosClient(f['endpoint'],dbutils.secrets.get(f['scope'],f['secret'])).get_database_client(f['database'])
 for name,key in {**CONTAINERS,'users':'user_id'}.items():real.create_container_if_not_exists(id=f['prefix']+name,partition_key=PartitionKey(path='/'+key))
 class Scoped:
  def get_container_client(self,name):
   assert name in {*CONTAINERS,'users'}
   return real.get_container_client(f['prefix']+name)
 db=Scoped()
 class Client:
  def get_database_client(self,name):
   assert name==f['database'];return db
 report={'state':'running','checks':{},'fixture_trips':len(f['trips']),'fixture_users':len(f['users'])}
 control=db.get_container_client('baseline_metrics')
 def save():control.upsert_item({'id':'qa-report','campaign_id':CONTROL,'payload':report})
 save()
 try:
  for u in f['users']:db.get_container_client('users').upsert_item({'id':u['user_id'],**u})
  for r in f['ledger']:
   store=FeatureDocuments(db,r['campaign_id'],'bonus-rewards');store.container.upsert_item(store.record(r))
  for b in f['bundles']:
   store=FeatureDocuments(db,b['campaign_id'],'missions');store.container.upsert_item(store.record(b))
  spark=SparkSession.builder.getOrCreate();spark.sql('CREATE SCHEMA IF NOT EXISTS '+f['schema'])
  table=f['schema']+'.final_trips'
  if not spark.catalog.tableExists(table):
   spark.createDataFrame([(json.dumps(t),) for t in f['trips']],'document_json string').write.format('delta').mode('append').saveAsTable(table)
  args=['weekly_managed_job','--cosmos-endpoint',f['endpoint'],'--database',f['database'],'--secret-scope',f['scope'],'--cosmos-secret-key',f['secret'],'--gold-table',table,'--output-schema',f['schema']]
  before={c:list(FeatureDocuments(db,c,'bonus-rewards').all()) for c in f['campaigns']}
  snapshots=[]
  for iteration in range(2):
   with patch('azure.cosmos.CosmosClient',return_value=Client()),patch.object(sys,'argv',args):weekly_managed_job.main()
   reader=WeeklyReader(db);rows={c:{n:reader.read(n,c,[]) for n in ['effective_personal_baseline','global_baseline','ranking','weekly_user_profile','next_week_missions','reward_ledger','final_trip_gold_input']} for c in f['campaigns']}
   snapshots.append(rows)
   report['iterations']=iteration+1;report['row_counts']={c:{n:len(v) for n,v in outputs.items()} for c,outputs in rows.items()};save()
  primary=f['campaigns'][0];small=f['campaigns'][1];first=snapshots[0]
  ready=[r for r in first[primary]['effective_personal_baseline'] if r['status']=='ready']
  assert len(ready)==6,('personal ready',len(ready))
  assert all(r['_global_snapshot']['status']=='ready' for r in ready)
  low=[r for r in first[small]['effective_personal_baseline'] if r['status']=='ready'];assert len(low)==5
  assert all(r['_global_snapshot']['status']=='collecting' for r in low)
  assert any(r['status']=='collecting' for r in first[primary]['effective_personal_baseline'])
  report['checks']['personal_and_global_eligibility']=True
  for c in f['campaigns']:
   after=FeatureDocuments(db,c,'bonus-rewards').all()
   clean=lambda v:sorted([{k:x for k,x in r.items() if not k.startswith('_')} for r in v],key=lambda r:r['id'])
   assert clean(after)==clean(before[c]),'weekly changed paid rewards'
   expected=sum(r['points'] for r in f['ledger'] if r['campaign_id']==c and r['kind']=='trip')
   assert sum(r['points'] for r in first[c]['reward_ledger'])==expected
   assert len(first[c]['next_week_missions'])>0 and len(first[c]['weekly_user_profile'])>0
   assert all(r.get('campaign_id')==c for r in first[c]['reward_ledger'])
   assert first[c]['ranking']==snapshots[1][c]['ranking'],'closed ranking changed on rerun'
   assert first[c]['effective_personal_baseline']==snapshots[1][c]['effective_personal_baseline'],'baseline changed on rerun'
  report['checks'].update(reward_ledger_unchanged=True,paid_trip_sum=True,missions_and_profiles=True,campaign_isolation=True,rerun_idempotency=True)
  report['state']='passed';save();print('QA_REPORT '+json.dumps(report),flush=True)
 except BaseException as e:
  report['state']='failed';report['error']=str(e)[:1500];save();raise
if __name__=='__main__':main()
