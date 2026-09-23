"""One explicitly selected sandbox trip -> isolated Delta result. Never writes Cosmos."""
import inspect,sys,os,json,argparse,time
from pathlib import Path
ROOT=Path(inspect.currentframe().f_code.co_filename).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['CANOPY_KTDB_REFERENCE_ROOT']=str(ROOT)  # existing Transit adapter's reference-code variable; not a KTDB model call
os.environ['CANOPY_TRANSIT_REFERENCE_DIR']=str(ROOT/'assets/transit')
from service.isolation import TABLES,require_table
from service.phone_model import PhoneModel,stamp

def select_points(rows,trip):
    expected=int(trip['expected_last_sequence'])
    if expected<2:raise ValueError('At least two GPS observations required')
    by_sequence={}
    for row in rows:
        if row['trip_id']!=trip['trip_id'] or row['user_id']!=trip['user_id']:raise ValueError('GPS ownership mismatch')
        seq=row['sequence']
        if type(seq)!=int or seq<1 or seq>expected:raise ValueError('Unexpected GPS sequence')
        p={k:row.get(k) for k in ['trip_id','user_id','sequence','event_time','lat','lon','accuracy','altitude_m']}
        p['event_time']=stamp(p['event_time']).isoformat()
        if seq in by_sequence and by_sequence[seq]!=p:raise ValueError('Conflicting duplicate sequence')
        by_sequence[seq]=p
    missing=sorted(set(range(1,expected+1))-set(by_sequence))
    if missing:
        raise ValueError(f'Incomplete GPS: expected={expected}, received={len(by_sequence)}, missing_sequence_sample={missing[:10]}; check ingestion and quarantine')
    return [by_sequence[i] for i in range(1,expected+1)]

def main():
    p=argparse.ArgumentParser();p.add_argument('--trip-id',required=True);p.add_argument('--user-id',required=True)
    a=p.parse_args()
    if not a.trip_id.strip() or not a.user_id.strip():raise ValueError('Specify test trip_id and user_id; no implicit production lookup')
    import sklearn
    if sklearn.__version__!='1.9.0':raise RuntimeError('Expected scikit-learn 1.9.0, got '+sklearn.__version__)
    from pyspark.sql import SparkSession,functions as F
    from delta.tables import DeltaTable
    from services.trip_processor import validate_result
    from services.trip_carbon import carbon_for
    spark=SparkSession.builder.getOrCreate();spark.conf.set('spark.sql.session.timeZone','UTC')
    gps,ended,target=(require_table(TABLES[r],r) for r in ['gps','ended','results'])
    matches=spark.table(ended).where((F.col('trip_id')==a.trip_id)&(F.col('user_id')==a.user_id)).orderBy(F.col('processing_generation').desc()).limit(100).collect()
    if not matches:raise ValueError('No matching trip_ended event in sandbox; send GPS and lifecycle events to the test hub')
    trip=matches[0].asDict();generation=trip['processing_generation']
    for row in matches:
        d=row.asDict()
        if d['processing_generation']==generation and any(d[k]!=trip[k] for k in ['started_at','ended_at','expected_last_sequence','campaign_id']):raise ValueError('Conflicting lifecycle events')
    for k in ['started_at','ended_at']:trip[k]=stamp(trip[k]).isoformat()
    rows=spark.table(gps).where((F.col('trip_id')==a.trip_id)&(F.col('user_id')==a.user_id)&(F.col('sequence')<=trip['expected_last_sequence'])).collect()
    points=select_points([r.asDict() for r in rows],trip)
    started=time.perf_counter();model=PhoneModel();result=model.result(trip,points)
    if result['segments']:
        validate_result(trip,result)
        carbon=carbon_for(result['segments'],'mode')
        result['carbon']={'kg_co2e':carbon.emission_kgco2e,'factor_version':carbon.factor_version,'policy_version':carbon.policy_version,'scope':'classified_segments_only'}
    result.update(user_id=a.user_id,processing_generation=generation,is_sandbox=True,model_sha256=model.sha256,sklearn_version=sklearn.__version__,elapsed_seconds=time.perf_counter()-started)
    document=json.dumps(result,ensure_ascii=False,allow_nan=False)
    spark.sql(f'CREATE TABLE IF NOT EXISTS {target} (user_id STRING, trip_id STRING, processing_generation BIGINT, document_json STRING) USING DELTA')
    frame=spark.createDataFrame([(a.user_id,a.trip_id,int(generation),document)],'user_id string, trip_id string, processing_generation long, document_json string')
    DeltaTable.forName(spark,target).alias('t').merge(frame.alias('s'),'t.user_id=s.user_id AND t.trip_id=s.trip_id AND t.processing_generation=s.processing_generation').whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    saved=spark.table(target).where((F.col('user_id')==a.user_id)&(F.col('trip_id')==a.trip_id)&(F.col('processing_generation')==int(generation))).select('document_json').collect()
    if len(saved)!=1 or json.loads(saved[0]['document_json'])!=result:
        raise RuntimeError('Stored sandbox result does not match the computed result')
    print(json.dumps({'status':result['status'],'quality':result['data_quality']['status'],'output_table':target,'model_sha256':model.sha256,'sklearn_version':sklearn.__version__,'elapsed_seconds':result['elapsed_seconds'],'gps_count':len(points),'window_count':len(result['transit_evidence']),'feature_count':len(model.bundle['feature_columns']),'modes':[s['mode'] for s in result['segments']],'carbon':result.get('carbon'),'stored_rows_for_trip_generation':len(saved),'readback_verified':True}))
if __name__=='__main__':main()
