"""One-off verified history copy before the personal worker takes app traffic.

Run only after previous final/weekly writers have stopped. Source is read-only;
target is a normal managed Delta table, never a pipeline-owned materialized view.
"""
import argparse,json,sys,inspect
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--target',required=True);a=p.parse_args()
 root=Path(inspect.currentframe().f_code.co_filename).resolve().parents[1]/'runtime'
 sys.path.insert(0,str(root/'cloud/azure/pipelines/databricks'))
 from pyspark.sql import SparkSession,functions as F
 from finalize_trip_pipeline import gold_frame,verify_document
 from trip_delta_store import table_name,assert_managed_delta
 table_name(a.source);table_name(a.target)
 if a.source==a.target:raise ValueError('source and target must differ')
 spark=SparkSession.builder.getOrCreate()
 docs=[json.loads(r.document_json) for r in spark.table(a.source).select('document_json').collect()]
 for doc in docs:verify_document(doc)
 if not docs:raise ValueError('No history to migrate')
 schema=gold_frame(spark,docs[0]).drop('document_json').schema
 frame=spark.createDataFrame([(json.dumps(d),) for d in docs],'document_json string').withColumn('body',F.from_json('document_json',schema)).select('body.*','document_json')
 spark.sql('CREATE SCHEMA IF NOT EXISTS '+'.'.join('`'+x+'`' for x in a.target.split('.')[:-1]))
 if not spark.catalog.tableExists(a.target):frame.write.format('delta').mode('error').saveAsTable(a.target)
 assert_managed_delta(spark,a.target)
 expected={(d['trip_id'],d['user_id'],d['processing_generation']):d['finalization_hash'] for d in docs}
 actual={(r.trip_id,r.user_id,r.processing_generation):r.finalization_hash for r in spark.table(a.target).select('trip_id','user_id','processing_generation','finalization_hash').collect()}
 if expected!=actual:raise ValueError('History readback mismatch; do not switch traffic')
 print(json.dumps({'verified_history_rows':len(expected),'source':a.source,'target':a.target}),flush=True)

if __name__=='__main__':main()


