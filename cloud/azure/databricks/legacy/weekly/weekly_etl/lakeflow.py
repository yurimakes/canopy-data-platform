"""Weekly ETL: pure DataFrame transformations; external publication is a later task."""
from downstream_bootstrap import activate
activate()
from pyspark import pipelines as dp
from pyspark.sql import SparkSession, functions as F, types as T
from weekly_etl import spark_contracts as C
from weekly_etl.domain import PACKET_SCHEMA, campaign_rows, ranking_rows, combined_rows, behavior_rows
from helpers.spark_baseline import build_personal_baseline, select_personal_ready_users, build_global_eligibility, build_global_baseline, build_baseline_gold
from helpers.baseline_eligibility import build_baseline_eligibility
from baseline_eligibility import load_eligibility_policy, evaluate_personal_eligibility, observation_context, week_evaluation_time
from build_behavior_change import RESULT_SCHEMA as BEHAVIOR_SCHEMA
from build_ranking import build_ranking
from helpers.campaign_kpi import build_campaign_kpi
from pathlib import Path
import yaml

spark=SparkSession.getActiveSession()
prefix=spark.conf.get('canopy.catalog')+'.'+spark.conf.get('canopy.gold_schema')
policy=load_eligibility_policy()
root=activate()
ranking_policy=yaml.safe_load((root/'cloud/azure/pipelines/databricks/ranking_policy.yaml').read_text(encoding='utf-8'))
baseline_version=yaml.safe_load((root/'cloud/azure/pipelines/databricks/baseline_policy.yaml').read_text(encoding='utf-8'))['policy_version']
def read(name):return spark.read.table(prefix+'.'+name)
def name(value):return prefix+'.'+value
def inputs(kind,schema):
    return read('stage_weekly_inputs').where(F.col('artifact')==kind).select(F.from_json('document_json',schema).alias('row')).select('row.*')
def packets(df,kind):
    return df.select(F.lit(kind).alias('artifact'),F.col('campaign_id'),F.to_json(F.struct('*')).alias('document_json'))

def grouped_packets(source,fn,schema):
    # Keep planning lazy: applyInPandas internally requests input columns before
    # the first pipeline update has materialized the upstream relations.
    grouped=source.groupBy('campaign_id').agg(F.collect_list(F.struct('artifact','campaign_id','document_json')).alias('_rows'))
    transform=F.udf(fn,T.ArrayType(T.StructType.fromDDL(schema)))
    return grouped.select(F.explode(transform('_rows')).alias('row')).select('row.*')

MEMBERSHIP='user_id string,campaign_id string,department_id string,joined_at string,left_at string'
LEDGER='reward_id string,trip_id string,user_id string,campaign_id string,week string,week_label string,points double,status string'

@dp.materialized_view(name=name('final_trip_gold_input'))
def final_input():
    return read('stage_weekly_trips').filter((F.col('status')=='ready') & ~F.coalesce(F.col('is_mock'),F.lit(False))).filter(F.coalesce(F.get_json_object('document_json','$.data_quality.status'),F.lit('complete'))!='partial')

@dp.materialized_view(name=name('weekly_gold'))
def weekly_gold():return C.calculate_weekly(read('final_trip_gold_input'))

@dp.materialized_view(name=name('commute_weekly_gold'))
def commute_weekly_gold():
    return C.calculate_weekly(read('final_trip_gold_input').filter(F.get_json_object('document_json','$.commute_verified')=='true'))

@dp.materialized_view(name=name('baseline_eligibility'))
def eligibility():
    return build_baseline_eligibility(read('commute_weekly_gold'),policy,C.PERSONAL_ELIGIBILITY_SCHEMA,week_evaluation_time,observation_context,evaluate_personal_eligibility,membership_df=inputs('campaign_membership_raw',MEMBERSHIP),commute_scope_verified=True)

@dp.materialized_view(name=name('personal_baseline'))
def personal():
    return build_personal_baseline(read('commute_weekly_gold'),read('baseline_eligibility'),baseline_policy_version=baseline_version,commute_scope_verified=True,eligibility_policy=policy)

@dp.materialized_view(name=name('personal_ready_users'))
def ready():return select_personal_ready_users(read('personal_baseline'),eligibility_policy=policy)

@dp.materialized_view(name=name('global_eligibility'))
def global_gate():return build_global_eligibility(read('personal_baseline'),read('personal_ready_users'),eligibility_policy=policy)

@dp.materialized_view(name=name('global_baseline'))
def global_baseline():return build_global_baseline(read('personal_ready_users'),read('global_eligibility'),baseline_policy_version=baseline_version,eligibility_policy=policy)

@dp.materialized_view(name=name('baseline_gold'))
def baseline_gold():return build_baseline_gold(read('personal_baseline'),read('global_baseline'),personal_fields=T.StructType.fromDDL(C.PERSONAL_SCHEMA).fieldNames(),global_fields=T.StructType.fromDDL(C.GLOBAL_SCHEMA).fieldNames(),validate_schema=False)

@dp.materialized_view(name=name('behavior_change'))
def behavior():
    source=read('weekly_gold').select('user_id','campaign_id','week',F.col('total_kg_co2e').alias('metric_value'))
    grouped=source.groupBy('user_id','campaign_id').agg(F.collect_list(F.struct('*')).alias('_rows'))
    transform=F.udf(behavior_rows,T.ArrayType(T.StructType.fromDDL(BEHAVIOR_SCHEMA)))
    return grouped.select(F.explode(transform('_rows')).alias('row')).select('row.*')

@dp.materialized_view(name=name('weekly_domain_packets'))
def domain():
    source=read('stage_weekly_inputs').select('artifact','campaign_id','document_json')
    source=source.unionByName(packets(read('final_trip_gold_input'),'trips')).unionByName(packets(read('weekly_gold'),'weekly_gold')).unionByName(packets(read('commute_weekly_gold'),'commute_weekly_gold'))
    # Keep the complete canonical Trip document for mission calculation.
    source=source.filter(F.col('artifact')!='trips').unionByName(read('final_trip_gold_input').select(F.lit('trips').alias('artifact'),'campaign_id','document_json'))
    return grouped_packets(source,campaign_rows,PACKET_SCHEMA)

def domain_table(artifact,schema):
    return read('weekly_domain_packets').filter(F.col('artifact')==artifact).select(F.from_json('document_json',schema).alias('row')).select('row.*')

@dp.materialized_view(name=name('mission_response_weekly'))
def responses():
    return domain_table('mission_response_weekly','campaign_id string,user_id string,week_start string,week_end string,assignment_id string,completed boolean')

@dp.materialized_view(name=name('reward_ledger'))
def reward_ledger():return inputs('reward_ledger_history',LEDGER)

@dp.materialized_view(name=name('reward_calculation'))
def rewards():
    return (read('reward_ledger').groupBy('user_id','campaign_id','week_label').agg(F.sum('points').alias('points')).withColumnRenamed('week_label','week')
        .withColumn('status',F.lit('already_paid')).withColumn('payable',F.lit(False)).withColumn('reason',F.lit('already_paid_per_trip'))
        .withColumn('point_reason',F.lit('sum_of_paid_trip_rewards')).withColumn('missions_completed_this_week',F.lit(0).cast('long')).withColumn('policy_version',F.lit('trip-ledger-summary-v1')))

@dp.materialized_view(name=name('ranking_raw'))
def ranking_raw():
    personal,department=build_ranking(read('reward_ledger'),inputs('campaign_membership_raw',MEMBERSHIP),ranking_policy)
    def projected(df,kind):
        return df.select('campaign_id','week',F.lit(kind).alias('ranking_type'),F.col('user_id') if kind=='personal' else F.lit(None).cast('string').alias('user_id'),F.col('department_id') if kind=='department' else F.lit(None).cast('string').alias('department_id'),F.col('score').cast('double').alias('reward_points'),F.col('rank').cast('long'),'policy_version','generated_at')
    return projected(personal,'personal').unionByName(projected(department,'department'))

@dp.materialized_view(name=name('ranking'))
def ranking():
    source=packets(read('ranking_raw'),'ranking_raw').unionByName(read('stage_weekly_inputs').filter(F.col('artifact').isin('previous_ranking','snapshot')).select('artifact','campaign_id','document_json'))
    return grouped_packets(source,ranking_rows,'document_json string').select(F.from_json('document_json',C.RANKING_DRAFT_SCHEMA+',confirmed boolean').alias('row')).select('row.*')

@dp.materialized_view(name=name('campaign_kpi'))
def kpi():return build_campaign_kpi(read('weekly_gold'),C.mission_kpi_input(read('mission_response_weekly')),read('behavior_change'),read('reward_ledger'),inputs('campaign_membership_raw',MEMBERSHIP),validate_schema=False,mission_has_week=False)

@dp.materialized_view(name=name('weekly_outputs_gold'))
def combined():
    source=read('weekly_domain_packets').select('artifact','campaign_id','document_json')
    for artifact in ['weekly_gold','baseline_gold','ranking','campaign_kpi']:
        source=source.unionByName(packets(read(artifact),artifact))
    return grouped_packets(source,combined_rows,'document_json string')
