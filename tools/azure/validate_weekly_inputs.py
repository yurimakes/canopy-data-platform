"""별도 테스트 캠페인의 입력 생성과 실제 Weekly 함수 검증. SQL Warehouse 사용 제외."""
import argparse
import ast
import json
import sys
from pathlib import Path


def generate_fixture(path):
    from datetime import datetime, timedelta, timezone
    from finalize_trip_pipeline import build_final_trip
    from services.mock_trip_processor import ConfirmationFixtureProcessor
    campaign = "pipeline_test_weekly_20260918"
    users, trips = [], []
    for n in range(1, 7):
        uid = f"{campaign}_u{n:02d}"
        users.append({"id": uid, "user_id": uid, "nickname": f"주간검증 {n}",
                      "created_at": "2026-08-31T00:00:00+09:00", "campaign_joined_at": "2026-08-31T00:00:00+09:00",
                      "campaign_id": campaign, "campaign_left_at": None, "department_id": None,
                      "data_origin": "synthetic_weekly_validation"})
        for j in range(7):
            start = datetime(2026, 9, 7 if j < 6 else 14, 8, tzinfo=timezone(timedelta(hours=9))) + timedelta(days=j if j < 6 else 0)
            trip = {"trip_id": f"{uid}_t{j+1:02d}", "user_id": uid, "campaign_id": campaign,
                    "processing_generation": 1, "started_at": start.isoformat(),
                    "ended_at": (start + timedelta(minutes=10)).isoformat()}
            envelope = {"trip": trip, "result": ConfirmationFixtureProcessor().process_trip(trip),
                        "completed_at": (start + timedelta(minutes=11)).isoformat()}
            trips.append(build_final_trip(envelope, allow_test_trip=True))
    payload = {"campaign_id": campaign, "evaluation_week": "2026-W38", "users": users, "trips": trips}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print("Generated synthetic users=6 trips=42; no Azure changes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['generate', 'seed', 'verify'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--workspace-root', required=True)
    args = parser.parse_args()
    root = Path(args.workspace_root)
    sys.path[:0] = [str(root / 'apps/api'), str(root / 'cloud/azure/pipelines/databricks'),
                   str(root / 'cloud/azure/pipelines/weekly_analysis')]
    if args.phase == 'generate':
        generate_fixture(args.input)
        return
    from pyspark.sql import SparkSession, Window, functions as F, types as T
    spark = SparkSession.builder.getOrCreate()
    spark.conf.set('spark.sql.session.timeZone', 'UTC')
    payload = json.loads(Path(args.input).read_text(encoding='utf-8'))
    campaign = payload['campaign_id']
    if not campaign.startswith('pipeline_test_weekly_'):
        raise ValueError('Test campaign required')
    gold_path = 'abfss://curated@stcanopydev5dt.dfs.core.windows.net/pipeline_test/trip_finalization/iphone_final_trips'
    membership_path = 'abfss://curated@stcanopydev5dt.dfs.core.windows.net/curated/campaign_membership_raw/'
    if args.phase == 'seed':
        from azure.cosmos import CosmosClient
        from azure.cosmos.exceptions import CosmosResourceNotFoundError, CosmosResourceExistsError
        from databricks.sdk.runtime import dbutils
        from delta.tables import DeltaTable
        from finalize_trip_pipeline import gold_frame, verify_document, canonical
        from sync_campaign_membership import run as sync_members
        docs = payload['trips']
        for doc in docs:
            verify_document(doc)
            assert doc['campaign_id'] == campaign and doc['is_mock'] is True
            assert doc['trip_id'].startswith('pipeline_test_weekly_')
        client = CosmosClient('https://cosmos-canopy-dev.documents.azure.com:443/', credential=dbutils.secrets.get(scope='canopy-trip-pipeline-test', key='cosmos-key'))
        users = client.get_database_client('canopy-db').get_container_client('users')
        for user in payload['users']:
            assert user['campaign_id'] == campaign and user['created_at'] == user['campaign_joined_at']
            assert user['data_origin'] == 'synthetic_weekly_validation'
            try:
                existing = users.read_item(user['id'], partition_key=user['user_id'])
            except CosmosResourceNotFoundError:
                try:
                    existing = users.create_item(user)
                except CosmosResourceExistsError:
                    existing = users.read_item(user['id'], partition_key=user['user_id'])
            if any(existing.get(k) != v for k, v in user.items()):
                raise ValueError('Existing user differs; no overwrite')
        schema = gold_frame(spark, docs[0]).drop('document_json').schema
        frame = spark.createDataFrame([(canonical(d),) for d in docs], 'document_json string').withColumn('body', F.from_json('document_json', schema)).select('body.*', 'document_json')
        target = DeltaTable.forPath(spark, gold_path)
        mismatches = target.toDF().alias('t').join(frame.alias('s'), ['user_id', 'trip_id']).where(F.col('t.finalization_hash') != F.col('s.finalization_hash')).limit(1).count()
        if mismatches:
            raise ValueError('Existing test Trip differs; no overwrite')
        target.alias('t').merge(frame.alias('s'), 't.trip_id=s.trip_id AND t.user_id=s.user_id').whenNotMatchedInsertAll().execute()
        assert spark.read.format('delta').load(gold_path).where(F.col('campaign_id') == campaign).count() == len(docs)
        sync_members(campaign, endpoint='https://cosmos-canopy-dev.documents.azure.com:443/', secret_scope='canopy-trip-pipeline-test', secret_key='cosmos-key')
        print(json.dumps({'phase': 'seed', 'campaign_id': campaign, 'users':len(payload['users']), 'trips':len(docs)}))
        return
    # 실제 파이프라인이 저장한 Weekly Gold를 입력으로 사용. 담당 함수 수정 제외.
    from helpers.baseline_eligibility import build_baseline_eligibility
    from helpers.spark_baseline import build_personal_baseline, select_personal_ready_users, build_global_eligibility, build_global_baseline
    from baseline_eligibility import load_eligibility_policy, week_evaluation_time, observation_context, evaluate_personal_eligibility
    from build_personal_baseline import load_policy
    source = root / 'cloud/azure/pipelines/weekly_analysis/weekly_pipeline.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    schema = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PERSONAL_ELIGIBILITY_SCHEMA' for t in node.targets):
            schema = ast.literal_eval(node.value)
    if schema is None:
        raise ValueError('Eligibility schema not found')
    if isinstance(schema, str):
        schema = T.StructType.fromDDL(schema)
    policy = load_eligibility_policy(str(root / 'shared/configs/baseline_eligibility.yaml'))
    baseline = load_policy(str(root / 'cloud/azure/pipelines/databricks/baseline_policy.yaml'))
    weekly = spark.read.table('dbw_canopy_dev.weekly_analysis_scaffold.weekly_gold').where(F.col('campaign_id') == campaign)
    rows = weekly.select('user_id', 'week', 'trip_count').collect()
    assert len(rows) == 12 and sum(r.trip_count for r in rows) == 42
    membership = spark.read.format('delta').load(membership_path).where(F.col('campaign_id') == campaign)
    eligibility = build_baseline_eligibility(weekly, policy, schema, week_evaluation_time, observation_context, evaluate_personal_eligibility, membership_df=membership, commute_scope_verified=True)
    # Python UDF 결과를 한 번 확정해 후속 검증의 중복 실행 방지.
    eligibility = spark.createDataFrame(eligibility.collect(), eligibility.schema)
    result = eligibility.where(F.col('week') == payload['evaluation_week']).collect()
    assert len(result) == 6 and all(r.status == 'ready' for r in result), str(result)
    personal = build_personal_baseline(weekly, eligibility, baseline_policy_version=baseline['policy_version'], commute_scope_verified=True, eligibility_policy=policy)
    personal = spark.createDataFrame(personal.collect(), personal.schema)
    ready = select_personal_ready_users(personal, eligibility_policy=policy)
    global_eligibility = build_global_eligibility(personal, ready, eligibility_policy=policy)
    global_result = build_global_baseline(ready, global_eligibility, baseline_policy_version=baseline['policy_version'], eligibility_policy=policy)
    output = global_result.where(F.col('week') == payload['evaluation_week']).collect()
    print('ELIGIBILITY', json.dumps([r.asDict(recursive=True) for r in result], default=str))
    print('GLOBAL', json.dumps([r.asDict(recursive=True) for r in output], default=str))
    assert len(output) == 1 and output[0].status == 'ready', str(output)
    reduced = ready.where(F.col('user_id') != payload['users'][0]['user_id'])
    below = build_global_eligibility(personal, reduced, eligibility_policy=policy).where(F.col('week') == payload['evaluation_week']).collect()
    assert len(below) == 1 and below[0].status == 'collecting' and below[0].eligible_participant_count == 5
    early = eligibility.where(F.col('week') == '2026-W37').collect()
    assert len(early) == 6 and all(r.status == 'collecting' for r in early)
    print('WEEKLY_VALIDATION_PASSED: six ready users; five-user Global blocked; no-prior-Trip week blocked')


if __name__ == '__main__':
    main()
