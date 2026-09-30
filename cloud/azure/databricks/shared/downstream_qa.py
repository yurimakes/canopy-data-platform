"""Synthetic downstream integration fixtures, restricted to dedicated QA namespaces.

This tests the Silver contract onward, not upstream GPS ingestion or ML accuracy.
No operation in this module targets canopy-db or the producer Silver schema.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from downstream_bootstrap import activate

CATALOG='dbw_canopy_trial'
SILVER='qa_silver_5dt024'
GOLD='qa_gold_5dt024'
DATABASE='canopy-qa-5dt024'
CAMPAIGN='qa_5dt024_four_weeks'


def fixtures():
    users=[];trips=[];segments=[];ends=[];points=[];ledger=[]
    joined='2026-08-01T00:00:00+00:00'
    for person in range(12):
        user=f'qa_5dt024_user_{person:02d}'
        users.append(dict(id=user,user_id=user,campaign_id=CAMPAIGN,department_id=f'qa_department_{person%2}',created_at=joined,campaign_joined_at=joined))
        for week in range(4):
            for journey in range(6):
                trip_id=f'qa_5dt024_w{week}_u{person:02d}_t{journey}'
                start=datetime(2026,8,24,0,tzinfo=timezone.utc)+timedelta(days=7*week+journey//2,hours=9*(journey%2))
                end=start+timedelta(minutes=20)
                mode='car' if journey<4-week else ('walk' if journey%2 else 'bus')
                home=dict(latitude=37.50,longitude=127.0,address='QA home')
                work=dict(latitude=37.54,longitude=127.0,address='QA work')
                trip=dict(id=trip_id,type='trip',trip_id=trip_id,user_id=user,campaign_id=CAMPAIGN,processing_generation=1,
                          expected_last_sequence=121,status='processing',result_owner='databricks',started_at=start.isoformat(),ended_at=end.isoformat(),
                          created_at=start.isoformat(),start_context={'home':home,'work':work},qa_fixture=True)
                trips.append(trip)
                segments.append(dict(trip_id=trip_id,user_id=user,processing_generation=1,segment_index=1,segment_id=trip_id+':s1',mode=mode,
                                     start_sequence=1,end_sequence=121,point_count=121,distance_m=5000.,confidence=.95,
                                     model_name='qa-silver-contract-fixture',model_version='1',start_time=start.isoformat(),end_time=end.isoformat(),
                                     segmented_at=(end+timedelta(seconds=10)).isoformat(),latest_prediction_at=(end+timedelta(seconds=8)).isoformat(),trip_end_parsed_at=(end+timedelta(seconds=2)).isoformat()))
                ends.append(dict(trip_id=trip_id,user_id=user,processing_generation=1,expected_last_sequence=121,result_owner='databricks'))
                for sequence in range(1,122):
                    fraction=(sequence-1)/120
                    if journey%2:fraction=1-fraction
                    points.append(dict(trip_id=trip_id,user_id=user,sequence=sequence,event_time=(start+timedelta(seconds=10*(sequence-1))).isoformat(),lat=37.50+.04*fraction,lon=127.,accuracy=5.))
                ledger.append(dict(id=trip_id+':paid',trip_id=trip_id,user_id=user,campaign_id=CAMPAIGN,kind='trip',status='paid',points=2,week=start.strftime('%G-W%V'),created_at=end.isoformat()))
    return dict(users=users,trips=trips,segments=segments,ends=ends,points=points,ledger=ledger)


def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['seed','verify']);a=p.parse_args()
    activate()
    from azure.cosmos import CosmosClient, PartitionKey
    from databricks.sdk.runtime import dbutils
    from pyspark.sql import SparkSession, functions as F
    from services.feature_documents import FeatureDocuments
    from services.weekly_cosmos import WeeklyReader
    spark=SparkSession.builder.getOrCreate();spark.conf.set('spark.sql.session.timeZone','UTC')
    client=CosmosClient('https://cosmos-canopy-dev.documents.azure.com:443/',credential=dbutils.secrets.get('canopy-downstream-5dt024','cosmos-key'))
    data=fixtures()
    if a.phase=='seed':
        db=client.create_database_if_not_exists(DATABASE)
        for container,key in {'trips':'user_id','users':'user_id','rewards':'user_id','missions':'user_id','mission_events':'user_id','ranking':'campaign_id','baseline_metrics':'campaign_id','mission-state':'pk'}.items():
            db.create_container_if_not_exists(container,partition_key=PartitionKey(path='/'+key))
        for name in ('users','trips'):
            target=db.get_container_client(name)
            for row in data[name]:target.upsert_item(row)
        target=db.get_container_client('rewards');features=FeatureDocuments(db,CAMPAIGN,'bonus-rewards')
        for row in data['ledger']:target.upsert_item(features.record(row))
        spark.sql(f'CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SILVER}`')
        spark.sql(f'CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{GOLD}`')
        schemas={
            'mode_segments':('segments','trip_id string,user_id string,processing_generation long,segment_index int,segment_id string,mode string,start_sequence long,end_sequence long,point_count long,distance_m double,confidence double,model_name string,model_version string,start_time timestamp,end_time timestamp,segmented_at timestamp,latest_prediction_at timestamp,trip_end_parsed_at timestamp'),
            'trip_ended_events':('ends','trip_id string,user_id string,processing_generation long,expected_last_sequence long,result_owner string'),
            'gps_observations':('points','trip_id string,user_id string,sequence long,event_time timestamp,lat double,lon double,accuracy double')}
        for name,(source,schema) in schemas.items():
            frame=spark.createDataFrame([(json.dumps(row),) for row in data[source]],'document_json string').select(F.from_json('document_json',schema).alias('row')).select('row.*')
            frame.write.format('delta').mode('overwrite').option('overwriteSchema','true').saveAsTable(f'{CATALOG}.{SILVER}.{name}')
        print(json.dumps({'qa_seed':True,'database':DATABASE,'users':len(data['users']),'trips':len(data['trips']),'weeks':4,'paid_points':576}));return
    db=client.get_database_client(DATABASE)
    rows=list(db.get_container_client('trips').query_items(query='SELECT * FROM c WHERE c.campaign_id=@campaign',parameters=[{'name':'@campaign','value':CAMPAIGN}],enable_cross_partition_query=True))
    assert len(rows)==288 and all(r['status']=='ready' and r['commute_verified'] for r in rows),'Trip publication/commute contract'
    from finalize_trip_pipeline import verify_document
    gold=spark.table(f'{CATALOG}.{GOLD}.final_trips').collect()
    assert len(gold)==288
    projected={r['trip_id']:r for r in rows}
    # Cosmos preserves lifecycle fields and adds _etag/_rid metadata. The hash
    # signs canonical Gold, not the entire enriched Cosmos envelope.
    for row in gold:
        document=json.loads(row.document_json);verify_document(document)
        actual=projected[row.trip_id]
        for field in ['finalization_hash','segments','carbon','confirmed_trip','commute_verified','processing_generation','status']:
            assert document[field]==actual[field],'Gold/Cosmos mismatch: '+field
    reader=WeeklyReader(db)
    names=['weekly_gold','personal_baseline','global_baseline','behavior_change','ranking','next_week_missions','reward_calculation']
    outputs={name:reader.read(name,CAMPAIGN,[]) for name in names}
    assert len(outputs['weekly_gold'])==48 and sum(r['trip_count'] for r in outputs['weekly_gold'])==288
    assert sum(r['total_distance_m'] for r in outputs['weekly_gold'])==1440000
    assert any(r['status']=='ready' for r in outputs['personal_baseline'])
    assert any(r['status']=='ready' for r in outputs['global_baseline'])
    assert any(r['status']=='changed' and r['change_kg_co2e']>0 for r in outputs['behavior_change'])
    assert len(outputs['next_week_missions'])==48
    paid=FeatureDocuments(db,CAMPAIGN,'bonus-rewards').all()
    assert len(paid)==288 and sum(r['points'] for r in paid)==576,'Weekly paid a second reward'
    assert sum(r['points'] for r in outputs['reward_calculation'])==576
    assert all(not r['payable'] for r in outputs['reward_calculation'])
    ranked=[r for r in outputs['ranking'] if r['ranking_type']=='personal']
    assert len(ranked)==48 and sum(r['reward_points'] for r in ranked)==576
    stable={name:[{k:v for k,v in row.items() if k!='generated_at'} for row in outputs[name]] for name in ['weekly_gold','personal_baseline','global_baseline','behavior_change','ranking']}
    stable={name:sorted(rows,key=lambda r:json.dumps(r,sort_keys=True)) for name,rows in stable.items()}
    digest=hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()
    control=db.get_container_client('baseline_metrics')
    previous=list(control.query_items(query="SELECT c.digest FROM c WHERE c.id='qa:verification'",enable_cross_partition_query=True))
    if previous:assert previous[0]['digest']==digest,'Repeated weekly computation changed stable results'
    control.upsert_item(dict(id='qa:verification',campaign_id=CAMPAIGN,digest=digest))
    print(json.dumps({'qa_verified':True,'trips':288,'weekly_rows':48,'mission_bundles':48,'paid_points':576,'replay_verified':bool(previous),'stable_digest':digest}))

if __name__=='__main__':main()
