"""Deployment gate on the target compute. Never creates Trips or reward payments."""
import argparse
import hashlib
import inspect
import json
import os
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

def verify_weekly(runtime='databricks'):
    """Isolated fixtures exercise the actual transforms, including Spark Connect."""
    import weekly
    from finalize_trip_pipeline import build_final_trip,ConfirmationFixtureProcessor
    with tempfile.TemporaryDirectory(prefix='canopy-release-weekly-') as temporary:
        root=Path(temporary);inputs=root/'inputs';inputs.mkdir()
        users=[];trips=[];ledger=[]
        for i in range(5):
            user={'user_id':'pipeline_test_release_user_'+str(i),'campaign_id':'pipeline_test_release_check',
                'department_id':'release_check_department','campaign_joined_at':'2026-09-01T00:00:00+00:00'}
            trip={k:user[k] for k in ('user_id','campaign_id')}
            trip.update(trip_id='pipeline_test_release_trip_'+str(i),processing_generation=1,
                started_at='2026-09-16T01:00:00+00:00',ended_at='2026-09-16T01:10:00+00:00')
            doc=build_final_trip({'trip':trip,'result':ConfirmationFixtureProcessor().process_trip(trip),
                'completed_at':'2026-09-16T01:11:00+00:00'},allow_test_trip=True)
            users.append(user);trips.append(doc)
            ledger.append({'reward_id':'release_reward_'+str(i),'trip_id':trip['trip_id'],**{k:user[k] for k in ('user_id','campaign_id')},
                'week':'2026-09-14','week_label':'2026-W38','points':42,'status':'paid'})
        for name,rows in {'users':users,'trips':trips,'reward_ledger_history':ledger}.items():
            (inputs/(name+'.json')).write_text(json.dumps(rows),encoding='utf-8')
        weekly.main(['--runtime',runtime,'--inputs',str(inputs),'--output',str(root/'weekly'),'--state',str(root/'state'),
            '--exported-ledger','--include-mock','--commute-verified'])
        generation=json.loads((root/'weekly/current.json').read_text())['generation']
        output=root/'weekly/generations'/generation
        paid=json.loads((output/'reward_ledger.json').read_text())
        if len(paid)!=5 or sum(r['points'] for r in paid)!=210:raise ValueError('Weekly paid ledger reconciliation failed')
        if any(r.get('payable') for r in json.loads((output/'reward_calculation.json').read_text())):raise ValueError('Weekly must not pay Trip rewards again')

def main():
    p=argparse.ArgumentParser()
    for name in ('cosmos-endpoint','database','trips-container','state-container','storage-url','container',
            'gps-table','gold-table','queue-table','secret-scope','cosmos-secret-key'):p.add_argument('--'+name,required=True)
    p.add_argument('--identity-secret-scope');p.add_argument('--storage-secret-key')
    a=p.parse_args();root=Path(inspect.currentframe().f_code.co_filename).resolve().parents[4]
    manifest=json.loads((root/'release-manifest.json').read_text())
    for name,digest in manifest.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Uploaded file checksum mismatch: '+name)
    assets=root/'runtime-assets'
    os.environ['CANOPY_SPEED_MODEL_ROOT']=str(assets/'speed-model')
    os.environ['CANOPY_KTDB_REFERENCE_ROOT']=str(assets/'reference-model')
    os.environ['CANOPY_KTDB_MODEL_PATH']=str(assets/'models/ktdb_population_baseline.pkl')
    os.environ['CANOPY_TRANSIT_REFERENCE_DIR']=str(assets/'transit')
    sys.path[:0]=[str(root),str(root/'tools/local'),str(root/'apps/api'),str(root/'cloud/azure/pipelines/databricks')]
    from model import LocalModel
    from datetime import datetime,timezone,timedelta
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    points=[{'event_time':(start+timedelta(seconds=i*5)).isoformat(),'lat':37.5+i*.00005,'lon':127.,'accuracy':5} for i in range(30)]
    if not LocalModel().predict(points):raise ValueError('Model produced no prediction')
    # This .pkl is a CatBoost native binary, not a Python/joblib pickle.
    from catboost import CatBoostClassifier
    reference_model=CatBoostClassifier()
    reference_model.load_model(str(assets/'models/ktdb_population_baseline.pkl'))
    from databricks.sdk.runtime import dbutils
    from pyspark.sql import SparkSession
    from trip_delta_store import table_name
    table_name(a.gps_table)
    spark=SparkSession.builder.getOrCreate()
    spark.table(a.gps_table).select('user_id','trip_id','sequence','event_time','lat','lon','accuracy').limit(0).collect()
    for target in {a.gold_table,a.queue_table}:
        table_name(target)
        probe_table=target.rsplit('.',1)[0]+'.canopy_release_check_'+uuid4().hex
        spark.createDataFrame([('release-check',)],'check string').write.format('delta').saveAsTable(probe_table)
        try:
            if spark.table(probe_table).count()!=1:raise ValueError('Delta readback failed')
        finally:spark.sql('DROP TABLE '+probe_table)
    from azure.identity import ClientSecretCredential
    from azure.cosmos import CosmosClient
    from azure.storage.blob import BlobServiceClient
    get=lambda key:dbutils.secrets.get(a.identity_secret_scope,key)
    context=ClientSecretCredential(get('azure-tenant-id'),get('azure-client-id'),get('azure-client-secret')) if a.identity_secret_scope else nullcontext(None)
    with context as identity:
        cosmos_credential=identity or dbutils.secrets.get(a.secret_scope,a.cosmos_secret_key)
        blob_credential=identity or dbutils.secrets.get(a.secret_scope,a.storage_secret_key)
        db=CosmosClient(a.cosmos_endpoint,credential=cosmos_credential).get_database_client(a.database)
        for name,pk in [('users','/user_id'),(a.trips_container,'/user_id'),(a.state_container,'/scope')]:
            if db.get_container_client(name).read()['partitionKey']['paths']!=[pk]:raise ValueError('Partition mismatch: '+name)
        keydb=CosmosClient(a.cosmos_endpoint,credential=dbutils.secrets.get(a.secret_scope,a.cosmos_secret_key)).get_database_client(a.database)
        trips=keydb.get_container_client(a.trips_container)
        probe_id='release-check-'+uuid4().hex
        trips.create_item({'id':probe_id,'user_id':probe_id,'type':'release_check'})
        try:trips.read_item(probe_id,partition_key=probe_id)
        finally:trips.delete_item(probe_id,partition_key=probe_id)
        container=BlobServiceClient(a.storage_url,credential=blob_credential).get_container_client(a.container)
        probe='release-check/'+uuid4().hex
        container.upload_blob(probe,b'canopy-release-check',overwrite=False)
        try:
            if container.download_blob(probe).readall()!=b'canopy-release-check':raise ValueError('Blob readback failed')
        finally:container.delete_blob(probe)
    verify_weekly()
    print(json.dumps({'runtime_check':'passed','model_inference':True,'gps_schema':True,'cosmos_read':True,'weekly_blob_write':True,'weekly_transforms':True}))

if __name__=='__main__':main()
