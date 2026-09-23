"""Unity Catalog tables -> weekly transforms -> managed Gold -> Cosmos app projections.
No ADLS/Blob storage paths are read by this job or by the app projection reader.
"""
import argparse,inspect,json,sys,tempfile
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(inspect.currentframe().f_code.co_filename).resolve().parents[4]
for folder in (ROOT,ROOT/'tools/local',ROOT/'apps/api',ROOT/'cloud/azure/pipelines/databricks',ROOT/'cloud/azure/pipelines/weekly_analysis'):
 sys.path.insert(0,str(folder))
def main():
 p=argparse.ArgumentParser()
 for name in ('cosmos-endpoint','database','secret-scope','cosmos-secret-key','gold-table','output-schema'):p.add_argument('--'+name,required=True)
 a=p.parse_args()
 from pyspark.sql import SparkSession,functions as F
 from databricks.sdk.runtime import dbutils
 from azure.cosmos import CosmosClient
 from trip_delta_store import table_name,quoted,assert_managed_delta
 from weekly_job import export_inputs
 from publish_weekly import validate
 from services.weekly_cosmos import WeeklyReader,publish,CONTROL,json_value
 import weekly
 table_name(a.gold_table);table_name(a.output_schema+'.validation')
 spark=SparkSession.builder.getOrCreate();spark.conf.set('spark.sql.session.timeZone','UTC')
 assert_managed_delta(spark,a.gold_table)
 trips=[json.loads(r.document_json) for r in spark.table(a.gold_table).select('document_json').collect()]
 trips=[t for t in trips if t.get('status')=='ready' and not t.get('is_mock') and not (t.get('start_context') or {}).get('simulation')]
 db=CosmosClient(a.cosmos_endpoint,credential=dbutils.secrets.get(a.secret_scope,a.cosmos_secret_key)).get_database_client(a.database)
 control=db.get_container_client('baseline_metrics')
 try:
  with tempfile.TemporaryDirectory(prefix='canopy-weekly-') as temporary:
   folder=Path(temporary)
   export_inputs(db,None,folder/'inputs',managed_trips=trips,feature_containers=True)
   campaigns={t['campaign_id'] for t in trips};reader=WeeklyReader(db)
   previous=[r for campaign in campaigns for r in reader.read('ranking',campaign,[])]
   (folder/'inputs/previous_ranking.json').write_text(json.dumps(previous),encoding='utf-8')
   weekly.main(['--runtime','databricks','--exported-ledger','--inputs',str(folder/'inputs'),'--output',str(folder/'weekly'),'--state',str(folder/'state')])
   pointer,directory,manifest=validate(folder/'weekly');outputs={}
   spark.sql('CREATE SCHEMA IF NOT EXISTS '+'.'.join('`'+v+'`' for v in a.output_schema.split('.')))
   # The immutable row envelope retains all original typed JSON fields, plus indexed scope columns.
   schema='generation string, ordinal long, campaign_id string, user_id string, week string, document_json string'
   for name in manifest:
    value=json_value(json.loads((directory/(name+'.json')).read_text(encoding='utf-8')));rows=value if isinstance(value,list) else [value]
    records=[(pointer['generation'],i,r.get('campaign_id'),r.get('user_id'),str(r.get('week') or ''),json.dumps(r,ensure_ascii=False,allow_nan=False)) for i,r in enumerate(rows)]
    table=a.output_schema+'.'+name
    spark.createDataFrame(records,schema).write.format('delta').mode('append').saveAsTable(table)
    assert_managed_delta(spark,table)
    saved=[json.loads(r.document_json) for r in spark.table(table).where(F.col('generation')==pointer['generation']).orderBy('ordinal').select('document_json').collect()]
    if saved!=rows:raise ValueError('Managed table readback mismatch: '+name)
    outputs[name]=saved if isinstance(value,list) else saved[0]
    print('Managed Gold verified:',table,len(saved),flush=True)
   print('Cosmos publication:',publish(db,pointer,outputs),flush=True)
   control.upsert_item({'id':'last-attempt','campaign_id':CONTROL,'payload':outputs['run']})
 except BaseException:
  control.upsert_item({'id':'last-attempt','campaign_id':CONTROL,'payload':{'completed_at':datetime.now(timezone.utc).isoformat(),'stages':{'weekly':{'status':'failed','error':'Weekly managed job failed; inspect Databricks run'}}}})
  raise
if __name__=='__main__':main()
