"""Declarative managed Gold computation. No Cosmos access or manual writes."""
from downstream_bootstrap import activate
activate()
import json
import pandas as pd
from pyspark import pipelines as dp
from pyspark.sql import SparkSession, functions as F
from final_trip.batch import calculate

spark=SparkSession.getActiveSession()
catalog=spark.conf.get('canopy.catalog')
schema=spark.conf.get('canopy.gold_schema')
prefix=f'{catalog}.{schema}'
def table(name): return spark.read.table(prefix+'.'+name)
def silver(name): return spark.read.table(f"{catalog}.{spark.conf.get('canopy.silver_schema','silver')}.{name}")


@dp.materialized_view(name=prefix+'.final_trips', comment='Canonical carbon-finalized Trips; producer Silver remains read-only')
def final_trips():
    keys=['trip_id','user_id','processing_generation']
    pending=table('stage_final_lifecycles').select(*keys,'document_json')
    segments=silver('mode_segments')
    ends=silver('trip_ended_events')
    gps=silver('gps_observations').select('trip_id','user_id','sequence','event_time','lat','lon','accuracy')
    # Bound scans and GPS coverage to the lifecycle's closed sequence range.
    segments=segments.join(pending.select(*keys),keys,'left_semi')
    ends=ends.join(pending.select(*keys),keys,'left_semi')
    gps=(gps.join(pending.select('trip_id','user_id',F.get_json_object('document_json','$.expected_last_sequence').cast('long').alias('_last')),['trip_id','user_id'])
         .filter((F.col('sequence')>=1)&(F.col('sequence')<=F.col('_last'))).drop('_last'))
    def packed(df,group,name):
        return df.groupBy(*group).agg(F.to_json(F.collect_list(F.struct(*[F.col(c) for c in df.columns]))).alias(name))
    candidate=(pending.join(packed(segments,keys,'segments'),keys,'left')
        .join(packed(ends,keys,'ends'),keys,'left')
        .join(packed(gps,['trip_id','user_id'],'points'),['trip_id','user_id'],'left'))
    fresh=candidate.mapInPandas(calculate,'trip_id string,user_id string,processing_generation long,document_json string')
    prior=table('stage_final_prior').select(*keys,'document_json')
    # The snapshot preserves historical Gold across later lifecycle status changes.
    merged=prior.join(fresh.select('trip_id','user_id'),['trip_id','user_id'],'left_anti').unionByName(fresh)
    from weekly_etl.spark_contracts import FINAL_TRIP_SCHEMA
    return merged.select(F.col('document_json').alias('_raw'),F.from_json('document_json',FINAL_TRIP_SCHEMA).alias('body')).select('body.*','_raw').drop('document_json').withColumnRenamed('_raw','document_json')
