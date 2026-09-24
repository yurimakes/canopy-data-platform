# Databricks notebook source
import os,sys,json,uuid
from datetime import datetime,timezone,timedelta
source_root = os.environ.get('CANOPY_DATABRICKS_SOURCE_ROOT')
if not source_root:
    raise RuntimeError('Set CANOPY_DATABRICKS_SOURCE_ROOT to the deployed Python source folder')
sys.path.insert(0, source_root)
from trip_prediction_wait import register,poll,retry
from pyspark.sql import functions as F
from delta.tables import DeltaTable
spark.conf.set("spark.sql.session.timeZone","UTC")
now=datetime.now(timezone.utc)
path="abfss://curated@stcanopydev5dt.dfs.core.windows.net/pipeline_test/trip_finalization/prediction_wait_1789559641"
path += "_" + uuid.uuid4().hex
schema="user_id string, trip_id string, processing_generation long, event_id string, campaign_id string, started_at timestamp, ended_at timestamp, expected_last_sequence long, result_owner string"
ends=spark.createDataFrame([("pipeline_test_user","pipeline_test_wait",1,"pipeline_test_end","pipeline_test_campaign",now-timedelta(seconds=10),now,2,"databricks")],schema)
register(spark,ends,path,now)
register(spark,ends,path,now+timedelta(seconds=60))
def row():return spark.read.format("delta").load(path).first()
assert row().attempts==0 and row().deadline_at.replace(tzinfo=timezone.utc)==now+timedelta(seconds=600)
poll(spark,path,"missing_catalog_for_test.missing.gps","missing_catalog_for_test.missing.ml",now)
assert row().attempts==1 and row().reason=="source_read_failed" and row().status=="waiting"
poll(spark,path,"missing_catalog_for_test.missing.gps","missing_catalog_for_test.missing.ml",now+timedelta(seconds=1))
assert row().attempts==1
poll(spark,path,"missing_catalog_for_test.missing.gps","missing_catalog_for_test.missing.ml",now+timedelta(seconds=601))
assert row().status=="timed_out" and row().envelope_json is None
retry(spark,path,"pipeline_test_user","pipeline_test_wait",1,"retry-1",now+timedelta(seconds=602))
assert row().status=="waiting" and row().attempts==0
poll(spark,path,"missing_catalog_for_test.missing.gps","missing_catalog_for_test.missing.ml",now+timedelta(seconds=1203))
assert row().status=="timed_out"
retry(spark,path,"pipeline_test_user","pipeline_test_wait",1,"retry-1",now+timedelta(seconds=1204))
assert row().status=="timed_out"
retry(spark,path,"pipeline_test_user","pipeline_test_wait",1,"retry-2",now+timedelta(seconds=1204))
assert row().status=="waiting"
conflict=ends.withColumn("expected_last_sequence",F.lit(3).cast("long"))
register(spark,conflict,path,now+timedelta(seconds=1205))
assert row().status=="failed" and row().reason=="conflicting_end_events"
dbutils.notebook.exit(json.dumps({"passed":True,"checks":["durable_queue","duplicate_end_keeps_deadline","source_error_retry","not_due_skipped","timeout","explicit_retry","duplicate_retry_no_reset","conflicting_end"],"queue_path":path}))
