"""Bounded diagnostic: real GPS/Gold/Cosmos path, one prepared Python/Spark process.

Only consumes explicitly reserved synthetic Trips for a single test user.
Reports timings to a private Blob; never changes rewards or fabricates results.
"""
import argparse
import hashlib
import inspect
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(inspect.currentframe().f_code.co_filename).resolve().parents[4]
sys.path[:0]=[str(ROOT/'cloud/azure/pipelines/databricks'),str(ROOT/'tools/local'),str(ROOT/'apps/api')]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',required=True)
    a=json.loads(p.parse_args().config)
    from databricks.sdk.runtime import dbutils
    from azure.storage.blob import BlobServiceClient
    blob=BlobServiceClient(a['storage_url'],credential=dbutils.secrets.get(a['scope'],a['storage_key'])).get_container_client(a['container'])
    report={'session':a['session'],'state':'initializing','stages':{},'trips':[]}
    def save():
        report['updated_at']=datetime.now(timezone.utc).isoformat()
        blob.upload_blob('performance/'+a['session']+'.json',json.dumps(report),overwrite=True)
    def measured(name,fn,target=None):
        started=time.perf_counter();report['active_stage']=name;save()
        value=fn()
        (target if target is not None else report['stages'])[name]=round(time.perf_counter()-started,3)
        save();return value
    try:
        from pyspark.sql import SparkSession
        from finalize_trip_pipeline import ProjectionStore,build_final_trip,save_gold,publish_cosmos,canonical
        from infer_trip_batch import read_gps,wait_for_gps,infer
        spark=measured('spark_session',lambda:SparkSession.builder.getOrCreate())
        os.environ['CANOPY_SPEED_MODEL_ROOT']=str(ROOT/'runtime-assets/speed-model')
        os.environ['CANOPY_KTDB_REFERENCE_ROOT']=str(ROOT/'runtime-assets/reference-model')
        os.environ['CANOPY_TRANSIT_REFERENCE_DIR']=str(ROOT/'runtime-assets/transit')
        from model import LocalModel
        from transit_fusion import runtime
        model=measured('model_load',LocalModel)
        measured('transit_reference_load',runtime)
        measured('spark_read_warmup',lambda:spark.table(a['gps_table']).limit(1).collect())
        store=measured('cosmos_connect',lambda:ProjectionStore(a['cosmos_endpoint'],a['database'],a['trips_container'],dbutils.secrets.get(a['scope'],a['cosmos_key'])))
        report['state']='ready';save()
        deadline=time.monotonic()+a.get('seconds',900)
        handled=set()
        while time.monotonic()<deadline and len(handled)<a.get('trip_count',2):
            rows=list(store.container.query_items(query="SELECT * FROM c WHERE c.user_id=@u AND c.status='processing' AND c.warm_benchmark_session=@s",
                parameters=[{'name':'@u','value':a['user_id']},{'name':'@s','value':a['session']}],partition_key=a['user_id']))
            for trip in rows:
                if trip['trip_id'] in handled or trip.get('trip_end_outbox',{}).get('status')!='published':continue
                event=trip['trip_end_outbox']['event']
                if event['processing_generation']!=trip['processing_generation']:raise ValueError('Generation mismatch')
                entry={'trip_id':trip['trip_id'],'stages':{},'detected_at':datetime.now(timezone.utc).isoformat()}
                report['trips'].append(entry);timings=entry['stages'];started=time.perf_counter()
                points=measured('gps_read_and_wait',lambda:wait_for_gps(lambda:read_gps(spark,a['gps_table'],trip),trip,timeout=180,interval=2),timings)
                entry['gps_count']=len(points)
                result,verified=measured('model_and_transit',lambda:infer(trip,points,model=model),timings)
                context={k:trip[k] for k in ('trip_id','user_id','campaign_id','started_at','ended_at','processing_generation')}
                document=measured('build_result',lambda:build_final_trip({'trip':context,'result':result,'completed_at':datetime.now(timezone.utc).isoformat()},lifecycle=trip),timings)
                document['commute_verified']=verified
                document['finalization_hash']=hashlib.sha256(canonical({k:v for k,v in document.items() if k!='finalization_hash'}).encode()).hexdigest()
                measured('gold_write_and_verify',lambda:save_gold(spark,a['gold_table'],document),timings)
                entry['publish_status']=measured('cosmos_publish',lambda:publish_cosmos(store,document),timings)
                entry['worker_seconds']=round(time.perf_counter()-started,3)
                entry['completed_at']=datetime.now(timezone.utc).isoformat();handled.add(trip['trip_id']);save()
            time.sleep(1)
        report['state']='completed' if len(handled)==a.get('trip_count',2) else 'timed_out';save()
    except Exception as exc:
        report['state']='failed';report['error']=type(exc).__name__+': '+str(exc)[:1200];save();raise

if __name__=='__main__':main()
