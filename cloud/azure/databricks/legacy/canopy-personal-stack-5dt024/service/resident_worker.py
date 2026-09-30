"""Continuously ready Trip worker: reuse the Python model and Spark session.

Consumes authenticated lifecycle outboxes, uses generation leases, and publishes
only after the canonical Gold write. Continuous Jobs restarts a failed worker.
"""
import argparse
import hashlib
import inspect
import json
import os
import sys
import time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4

SERVICE=Path(inspect.currentframe().f_code.co_filename).resolve().parent
ROOT=SERVICE.parent/'runtime'
sys.path[:0]=[str(ROOT/'cloud/azure/pipelines/databricks'),str(ROOT/'tools/local'),str(ROOT/'apps/api')]
sys.path.append(str(SERVICE))

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=json.loads(p.parse_args().config)
    from databricks.sdk.runtime import dbutils
    from pyspark.sql import SparkSession,functions as F
    from azure.storage.blob import BlobServiceClient
    from services.cosmos_service import Conflict
    from finalize_trip_pipeline import ProjectionStore,build_final_trip,save_gold,read_gold,publish_cosmos,canonical,publish_wait_failure
    from infer_trip_batch import wait_for_gps,infer
    from gps_reader import read_gps
    import trip_delta_store as storage
    worker=str(uuid4())
    blob=BlobServiceClient(a['storage_url'],credential=dbutils.secrets.get(a['scope'],a['storage_key'])).get_container_client(a['container'])
    report={'worker_id':worker,'state':'initializing','stages':{},'trip_count':0}
    def status():
        report['updated_at']=datetime.now(timezone.utc).isoformat()
        blob.upload_blob('performance/resident-status.json',json.dumps(report),overwrite=True)
    def timed(name,fn,metrics):
        report['active_stage']=name;status();start=time.perf_counter()
        value=fn();metrics[name]=round(time.perf_counter()-start,3);status();return value
    os.environ['CANOPY_SPEED_MODEL_ROOT']=str(ROOT/'runtime-assets/speed-model')
    os.environ['CANOPY_KTDB_REFERENCE_ROOT']=str(ROOT/'runtime-assets/reference-model')
    os.environ['CANOPY_TRANSIT_REFERENCE_DIR']=str(ROOT/'runtime-assets/transit')
    from phone_model import PhoneModel as LocalModel
    from transit_fusion import runtime
    spark=timed('spark_session',lambda:SparkSession.builder.getOrCreate(),report['stages'])
    spark.conf.set('spark.sql.session.timeZone','UTC')
    model=timed('model_load',LocalModel,report['stages'])
    timed('transit_reference_load',runtime,report['stages'])
    timed('gps_read_warmup',lambda:spark.table(a['gps_table']).limit(1).collect(),report['stages'])
    store=ProjectionStore(a['cosmos_endpoint'],a['database'],a['trips_container'],dbutils.secrets.get(a['scope'],a['cosmos_key']))
    from live_predictions import start_live_predictions
    start_live_predictions(spark,store,model,a['gps_table'])
    report['state']='ready';report['active_stage']='waiting';status();last_heartbeat=time.monotonic()
    while True:
        now=datetime.now(timezone.utc)
        rows=list(store.container.query_items(query="SELECT TOP 20 * FROM c WHERE c.type='trip' AND c.status='processing' AND c.result_owner='databricks' AND c.trip_end_outbox.status='published' AND (NOT IS_DEFINED(c.resident_lease_until) OR c.resident_lease_until < @now)",
            parameters=[{'name':'@now','value':now.isoformat()}],enable_cross_partition_query=True))
        for candidate in rows:
            trip=store.read(candidate['trip_id'],candidate['user_id'])
            if trip['status']!='processing' or trip.get('resident_lease_until','')>datetime.now(timezone.utc).isoformat():continue
            trip.update(resident_worker_id=worker,resident_lease_until=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat())
            try:trip=store.replace(trip)
            except Conflict:continue
            started=time.perf_counter();metrics={};entry={'worker_id':worker,'trip_id':trip['trip_id'],'generation':trip['processing_generation'],'detected_at':datetime.now(timezone.utc).isoformat(),'stages':metrics}
            report.update(state='processing',trip_id=trip['trip_id']);status()
            try:
                event=trip['trip_end_outbox']['event']
                if event['processing_generation']!=trip['processing_generation'] or event['result_owner']!='databricks':raise ValueError('Invalid lifecycle generation')
                def existing():
                    if not storage.exists(spark,a['gold_table']):return None
                    rows=storage.read(spark,a['gold_table']).where((F.col('user_id')==trip['user_id'])&(F.col('trip_id')==trip['trip_id'])&(F.col('processing_generation')==trip['processing_generation'])).select('document_json').limit(1).collect()
                    return json.loads(rows[0].document_json) if rows else None
                document=timed('existing_gold',existing,metrics)
                if document is None:
                    points=timed('gps_read_and_wait',lambda:wait_for_gps(lambda:read_gps(spark,a['gps_table'],trip,a.get('gps_history_table')),trip,timeout=600,interval=1),metrics)
                    entry['gps_count']=len(points)
                    result,verified=timed('model_and_transit',lambda:infer(trip,points,model=model),metrics)
                    context={k:trip[k] for k in ('trip_id','user_id','campaign_id','started_at','ended_at','processing_generation')}
                    document=build_final_trip({'trip':context,'result':result,'completed_at':datetime.now(timezone.utc).isoformat()},lifecycle=trip)
                    document['commute_verified']=verified
                    document['finalization_hash']=hashlib.sha256(canonical({k:v for k,v in document.items() if k!='finalization_hash'}).encode()).hexdigest()
                    timed('gold_write_and_verify',lambda:save_gold(spark,a['gold_table'],document),metrics)
                entry['publish_status']=timed('cosmos_publish',lambda:publish_cosmos(store,document),metrics)
                entry['state']='ready'
            except Exception as exc:
                entry.update(state='failed',error=type(exc).__name__+': '+str(exc)[:1200])
                publish_wait_failure(store,{**trip,'status':'failed','reason':'resident_execution_failed'})
            entry['worker_seconds']=round(time.perf_counter()-started,3);entry['completed_at']=datetime.now(timezone.utc).isoformat()
            blob.upload_blob('performance/trips/'+trip['trip_id']+'.json',json.dumps(entry),overwrite=True)
            report.update(state='ready',active_stage='waiting',last_trip=entry,trip_count=report['trip_count']+1);status()
        if time.monotonic()-last_heartbeat>10:status();last_heartbeat=time.monotonic()
        time.sleep(1)

if __name__=='__main__':main()
