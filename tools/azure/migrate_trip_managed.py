"""기존 Trip Delta를 Managed Table로 복사하고 입력·집계·재처리 동등성 검증.

원본 경로와 Cosmos 변경 없음. Trip Job이 실행 중이지 않은 전환 구간에서 실행.
검증 성공 후에만 Job 인자와 Weekly 입력을 전환.
"""
import argparse
import ast
import copy
import json
from pathlib import Path
import sys
from uuid import uuid4


def equal_rows(left, right):
    if left.columns != right.columns:
        raise ValueError("source and target columns differ")
    # 전체 중첩 컬럼과 document_json까지 비교. 키 개수만 같은 잘못된 이전 방지.
    if left.exceptAll(right).limit(1).count() or right.exceptAll(left).limit(1).count():
        raise ValueError("source and target rows differ")


def migrate(spark, source, target, keys):
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    import trip_delta_store as storage
    original = DeltaTable.forPath(spark, source)
    version = original.history(1).select("version").first().version
    frame = spark.read.format("delta").option("versionAsOf", version).load(source)
    if frame.groupBy(*keys).count().where("count > 1").limit(1).count():
        raise ValueError("duplicate source keys")
    for key in keys:
        if frame.where(F.col(key).isNull()).limit(1).count():
            raise ValueError("null source key: " + key)
    storage.initialize(spark, target, frame)
    existing = storage.read(spark, target)
    if existing.exceptAll(frame).limit(1).count():
        raise ValueError("target contains unexpected rows; refusing overwrite")
    (storage.delta(spark, target).alias("t").merge(frame.alias("s"),
        " AND ".join("t." + k + " = s." + k for k in keys))
        .whenNotMatchedInsertAll().execute())
    equal_rows(frame, storage.read(spark, target))
    if original.history(1).select("version").first().version != version:
        raise ValueError("source changed during migration; do not switch consumers")
    print(json.dumps({"target": target, "source_version": version, "rows": frame.count(), "verified": True}), flush=True)
    return frame


def verify_weekly(spark, root, source, table):
    from pyspark.sql import functions as F, Window
    path = root / "cloud/azure/pipelines/weekly_analysis/weekly_pipeline.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    names = {"MODES", "LOW_CARBON_MODES", "TRANSIT_MODES", "SHORT_CAR_MAX_DISTANCE_M"}
    nodes = []
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            nodes.append(node)
        if isinstance(node, ast.FunctionDef) and (node.name == "final_trip_gold_input" or node.lineno >= next(n.lineno for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "calculate_weekly")):
            node = copy.deepcopy(node)
            node.decorator_list = []
            nodes.append(node)
    namespace = {"spark": spark, "F": F, "Window": Window, "FINAL_TRIP_TABLE": table}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    # 실제 Weekly 계산 함수를 사용하되 파이프라인 등록과 출력 쓰기는 실행하지 않음.
    actual = namespace["calculate_weekly"](namespace["final_trip_gold_input"]())
    old = namespace["calculate_weekly"](source.where(F.col("status") == "ready"))
    # 합산 순서 변경에 따른 부동소수점 오차만 허용(소수점 9자리).
    def comparable(df):
        return df.select(*[F.round(F.col(c), 9).alias(c) if kind in ("double", "float") else F.col(c) for c, kind in df.dtypes])
    equal_rows(comparable(old), comparable(actual))
    fixture = actual.where(F.col("campaign_id") == "pipeline_test_weekly_20260918")
    rows = fixture.select("user_id", "week", "trip_count").collect()
    if rows and (len(rows) != 12 or sum(r.trip_count for r in rows) != 42):
        raise ValueError("six-user fixture weekly counts differ")
    print(json.dumps({"weekly_rows": actual.count(), "fixture_trips": sum(r.trip_count for r in rows), "weekly_equal": True}), flush=True)


def verify_storage(spark, root, schema):
    from datetime import datetime, timedelta, timezone
    from finalize_trip_pipeline import build_final_trip, save_gold
    from services.mock_trip_processor import ConfirmationFixtureProcessor
    from trip_prediction_wait import register
    import trip_delta_store as storage
    suffix = uuid4().hex
    gold, queue = (schema + ".managed_validation_" + n + "_" + suffix for n in ("gold", "queue"))
    trip = {"trip_id": "pipeline_test_migration", "user_id": "pipeline_test_migration",
        "campaign_id": "pipeline_test_migration", "processing_generation": 1,
        "started_at": "2026-09-16T01:00:00+00:00", "ended_at": "2026-09-16T01:10:00+00:00"}
    envelope = {"trip": trip, "completed_at": "2026-09-16T01:11:00+00:00",
        "result": ConfirmationFixtureProcessor().process_trip(trip)}
    try:
        doc = build_final_trip(envelope, allow_test_trip=True)
        save_gold(spark, gold, doc)
        save_gold(spark, gold, doc)
        if storage.read(spark, gold).count() != 1:
            raise ValueError("duplicate replay inserted rows")
        changed = copy.deepcopy(envelope)
        changed["completed_at"] = "2026-09-16T01:12:00+00:00"
        try:
            save_gold(spark, gold, build_final_trip(changed, allow_test_trip=True))
        except ValueError as exc:
            if "conflicting result" not in str(exc):
                raise
        else:
            raise ValueError("same-generation conflicting result accepted")
        changed["trip"]["processing_generation"] = 2
        newer = build_final_trip(changed, allow_test_trip=True)
        save_gold(spark, gold, newer)
        try:
            save_gold(spark, gold, doc)
        except ValueError as exc:
            if "stale processing" not in str(exc):
                raise
        else:
            raise ValueError("stale generation accepted")
        now = datetime.now(timezone.utc)
        fields = ["user_id", "trip_id", "processing_generation", "event_id", "campaign_id", "started_at", "ended_at", "expected_last_sequence", "result_owner"]
        event = {**trip, "event_id": suffix, "started_at": now - timedelta(minutes=10), "ended_at": now,
            "expected_last_sequence": 10, "result_owner": "databricks"}
        ends = spark.createDataFrame([tuple(event[k] for k in fields)], "user_id string, trip_id string, processing_generation long, event_id string, campaign_id string, started_at timestamp, ended_at timestamp, expected_last_sequence long, result_owner string")
        register(spark, ends, queue, now)
        before = storage.read(spark, queue).first().deadline_at
        register(spark, ends, queue, now + timedelta(minutes=1))
        rows = storage.read(spark, queue).collect()
        if len(rows) != 1 or rows[0].deadline_at != before:
            raise ValueError("queue replay reset deadline")
        print("MANAGED_STORAGE_PASSED: replay, generation conflict, stale result, queue deadline", flush=True)
    finally:
        # 이번 실행에서 임의 ID로 만든 검증 테이블만 정리. 입력·이전 대상 테이블 제외.
        for target in (gold, queue):
            spark.sql("DROP TABLE IF EXISTS " + storage.quoted(target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--gold-source", required=True)
    parser.add_argument("--queue-source", required=True)
    parser.add_argument("--gold-table", required=True)
    parser.add_argument("--queue-table", required=True)
    args = parser.parse_args()
    root = Path(args.workspace_root)
    sys.path[:0] = [str(root / "cloud/azure/pipelines/databricks"), str(root / "apps/api")]
    import trip_delta_store as storage
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    for table in (args.gold_table, args.queue_table):
        storage.table_name(table)
        if not storage.test_target(table):
            raise ValueError("development migration requires sandbox/pipeline_test schema")
    if args.gold_table == args.queue_table:
        raise ValueError("Gold and queue must use separate tables")
    verify_storage(spark, root, ".".join(args.gold_table.split(".")[:2]))
    source = migrate(spark, args.gold_source, args.gold_table, ["user_id", "trip_id"])
    migrate(spark, args.queue_source, args.queue_table, ["user_id", "trip_id", "processing_generation"])
    verify_weekly(spark, root, source, args.gold_table)
    print("MANAGED_MIGRATION_PASSED: source retained; Cosmos unchanged", flush=True)


if __name__ == "__main__":
    main()
