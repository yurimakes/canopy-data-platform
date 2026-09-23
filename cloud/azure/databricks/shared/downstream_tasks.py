"""Job boundary tasks: snapshot external inputs, run finite ETL, publish outputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
from downstream_bootstrap import activate


def arguments():
    p=argparse.ArgumentParser()
    p.add_argument('phase',choices=['final-cycle','prepare-final','publish-final','prepare-weekly','publish-weekly','run-pipeline'])
    for key in ['catalog','gold-schema','cosmos-endpoint','database','secret-scope','cosmos-secret-key','run-id']:
        p.add_argument('--'+key,required=True)
    p.add_argument('--pipeline-id')
    p.add_argument('--publish-mode',choices=['publish','validate'],default='publish')
    return p.parse_args()


def main(a=None):
    a=a or arguments();activate()
    if a.phase=='final-cycle':
        # Continuous Jobs prohibit task dependencies; one bounded task owns the sequence.
        for phase in ['prepare-final','run-pipeline','publish-final']:
            main(argparse.Namespace(**{**vars(a),'phase':phase}))
        return
    from pyspark.sql import SparkSession, functions as F
    from azure.cosmos import CosmosClient
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.runtime import dbutils
    from trip_delta_store import table_name
    prefix=a.catalog+'.'+a.gold_schema
    table_name(prefix+'.validation')
    if a.gold_schema in ('silver','bronze'):raise ValueError('refusing upstream output schema')
    w=WorkspaceClient()
    if a.phase=='run-pipeline':
        spec=w.pipelines.get(a.pipeline_id).spec
        if spec.name not in ('[dev 5dt024] canopy-final-trip-etl-trial','[dev 5dt024] canopy-final-trip-etl-qa'):raise ValueError('not the owned final-trip pipeline')
        if spec.configuration.get('canopy.gold_schema')!=a.gold_schema:raise ValueError('output schema differs')
        update=w.pipelines.start_update(pipeline_id=a.pipeline_id).update_id
        try:
            deadline=time.monotonic()+1800
            while time.monotonic()<deadline:
                state=w.pipelines.get_update(a.pipeline_id,update).update.state.value
                if state=='COMPLETED':
                    print(json.dumps({'pipeline_update':update,'state':state}));return
                if state in ('FAILED','CANCELED'):raise RuntimeError('Owned final ETL '+state)
                time.sleep(5)
            raise TimeoutError('Owned final ETL timeout')
        except BaseException:
            w.pipelines.stop(a.pipeline_id)
            raise
    spark=SparkSession.builder.getOrCreate();spark.conf.set('spark.sql.session.timeZone','UTC')
    db=CosmosClient(a.cosmos_endpoint,credential=dbutils.secrets.get(a.secret_scope,a.cosmos_secret_key)).get_database_client(a.database)
    def read(table):return spark.table(prefix+'.'+table)
    def write(table,frame):frame.write.format('delta').mode('overwrite').option('overwriteSchema','true').saveAsTable(prefix+'.'+table)
    def json_rows(rows,schema):
        frame=spark.createDataFrame([(json.dumps(r,default=str),) for r in rows],'document_json string')
        return frame.select(F.col('document_json').alias('_raw'),F.from_json('document_json',schema).alias('body')).select('body.*','_raw').drop('document_json').withColumnRenamed('_raw','document_json')
    from weekly_etl.spark_contracts import FINAL_TRIP_SCHEMA
    def snapshot(kind):
        table='stage_'+kind+'_snapshot'
        # A task retry reuses its frozen snapshot rather than mixing input versions.
        if spark.catalog.tableExists(prefix+'.'+table):
            r=read(table).first()
            if r and r.run_id==a.run_id:return None
        return {'run_id':a.run_id,'created_at':datetime.now(timezone.utc).isoformat()}
    def save_snapshot(kind,value):write('stage_'+kind+'_snapshot',spark.createDataFrame([(value['run_id'],value['created_at'])],'run_id string,created_at string'))
    def check_snapshot(kind):
        r=read('stage_'+kind+'_snapshot').first()
        if not r or r.run_id!=a.run_id:raise ValueError('snapshot belongs to another run')
        return r
    if a.phase=='prepare-final':
        meta=snapshot('final')
        if meta is None:return
        spark.sql('CREATE SCHEMA IF NOT EXISTS '+'.'.join('`'+s+'`' for s in prefix.split('.')))
        pending=list(db.get_container_client('trips').query_items(query="SELECT * FROM c WHERE c.type='trip' AND c.result_owner='databricks' AND (c.status='processing' OR (c.status='ready' AND (NOT IS_DEFINED(c.endpoint_observations) OR IS_NULL(c.endpoint_observations))))",enable_cross_partition_query=True))
        write('stage_final_lifecycles',json_rows(pending,'trip_id string,user_id string,processing_generation long'))
        if spark.catalog.tableExists(prefix+'.final_trips'):
            prior=[json.loads(r.document_json) for r in read('final_trips').select('document_json').collect()]
        else:prior=[]
        write('stage_final_prior',json_rows(prior,'trip_id string,user_id string,processing_generation long'))
        save_snapshot('final',meta);print(json.dumps({'pending':len(pending),'prior':len(prior)}));return
    if a.phase=='publish-final':
        check_snapshot('final')
        from finalize_trip_pipeline import ProjectionStore,publish_cosmos,verify_document
        from final_trip.adapter import publish_with_endpoint_repair
        store=ProjectionStore(a.cosmos_endpoint,a.database,'trips',dbutils.secrets.get(a.secret_scope,a.cosmos_secret_key))
        count=0
        pending=read('stage_final_lifecycles').select('trip_id','user_id','processing_generation')
        for row in read('final_trips').join(pending,['trip_id','user_id','processing_generation']).select('document_json').toLocalIterator():
            document=json.loads(row.document_json);verify_document(document)
            if a.publish_mode=='publish':publish_with_endpoint_repair(store,document)
            count+=1
        print(json.dumps({'mode':a.publish_mode,'final_trip_count':count}));return
    if a.phase=='prepare-weekly':
        meta=snapshot('weekly')
        if meta is None:return
        spark.sql('CREATE SCHEMA IF NOT EXISTS '+'.'.join('`'+s+'`' for s in prefix.split('.')))
        from weekly_job import export_inputs
        from services.weekly_cosmos import WeeklyReader
        trips=[json.loads(r.document_json) for r in read('final_trips').select('document_json').collect()]
        trips=[t for t in trips if t.get('status')=='ready' and not t.get('is_mock') and not (t.get('start_context') or {}).get('simulation')]
        with tempfile.TemporaryDirectory() as folder:
            export_inputs(db,None,folder,managed_trips=trips,feature_containers=True)
            values={p.stem:json.loads(p.read_text()) for p in Path(folder).glob('*.json') if p.stem!='trips'}
        campaigns=sorted({t['campaign_id'] for t in trips}|{u['campaign_id'] for u in values['users']})
        values['campaign_membership_raw']=[{'user_id':u['user_id'],'campaign_id':u['campaign_id'],'department_id':u.get('department_id'),'joined_at':u.get('campaign_joined_at') or u.get('created_at'),'left_at':u.get('campaign_left_at')} for u in values['users']]
        reader=WeeklyReader(db)
        values['previous_ranking']=[r for c in campaigns for r in reader.read('ranking',c,[])]
        values['snapshot']=[{**meta,'campaign_id':c} for c in campaigns]
        records=[(name,row['campaign_id'],json.dumps(row,default=str)) for name,rows in values.items() for row in rows]
        write('stage_weekly_inputs',spark.createDataFrame(records,'artifact string,campaign_id string,document_json string'))
        write('stage_weekly_trips',json_rows(trips,FINAL_TRIP_SCHEMA))
        save_snapshot('weekly',meta);print(json.dumps({'trips':len(trips),'campaigns':len(campaigns)}));return
    if a.phase=='publish-weekly':
        meta=check_snapshot('weekly')
        from services.weekly_cosmos import json_value,publish,CONTROL
        from weekly_ledger import validate_paid_ledger
        outputs={}
        names=['final_trip_gold_input','weekly_gold','commute_weekly_gold','baseline_eligibility','personal_baseline','personal_ready_users','global_eligibility','global_baseline','baseline_gold','behavior_change','reward_ledger','reward_calculation','ranking','campaign_kpi']
        # JSON serialization uses Spark's UTC timestamps and avoids Python datetime values in Cosmos.
        for name in names:
            df=read(name)
            outputs[name]=[json.loads(r.value) for r in df.select(F.to_json(F.struct(*[F.col(c) for c in df.columns])).alias('value')).collect()]
        for row in read('weekly_domain_packets').collect():outputs.setdefault(row.artifact,[]).append(json.loads(row.document_json))
        for name in ['mission_progress','mission_response_weekly','weekly_user_profile','next_week_missions','effective_personal_baseline']:outputs.setdefault(name,[])
        outputs['weekly_outputs_gold']=[json.loads(r.document_json) for r in read('weekly_outputs_gold').collect()]
        validate_paid_ledger(outputs['reward_ledger'])
        if any(r.get('payable') for r in outputs['reward_calculation']):raise ValueError('weekly payment forbidden')
        if not outputs['weekly_gold']:
            print(json.dumps({'status':'waiting_for_final_trips','published':False}));return
        outputs['run']={'completed_at':meta.created_at,'reward_mode':'trip-ledger-only','environment':'databricks','stages':{k:{'status':'passed','rows':len(v)} for k,v in outputs.items()}}
        outputs=json_value(outputs)
        pointer={'generation':hashlib.md5(a.run_id.encode()).hexdigest(),'completed_at':meta.created_at}
        if a.publish_mode=='publish':
            print(publish(db,pointer,outputs));db.get_container_client('baseline_metrics').upsert_item({'id':'last-attempt','campaign_id':CONTROL,'payload':outputs['run']})
        print(json.dumps({'mode':a.publish_mode,'artifacts':{k:len(v) for k,v in outputs.items() if isinstance(v,list)}}))

if __name__=='__main__':main()
