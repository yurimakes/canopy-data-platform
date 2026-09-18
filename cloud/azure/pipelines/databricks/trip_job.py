"""Existing Job entrypoint for one explicit Trip end. No changes to ML pipelines."""
import argparse
import json
import sys
import inspect
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(inspect.currentframe().f_code.co_filename).resolve().parent
sys.path.insert(0, str(HERE))
from finalize_trip_pipeline import build_final_trip, save_gold, read_gold, publish_cosmos, publish_wait_failure, ProjectionStore
from trip_prediction_wait import register, poll
import trip_delta_store as storage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--end-event", required=True)
    parser.add_argument("--input-mode", choices=("mock", "ml"), required=True)
    storage.add_target(parser, "gold")
    storage.add_target(parser, "queue")
    parser.add_argument("--cosmos-endpoint", required=True)
    parser.add_argument("--secret-scope", required=True)
    parser.add_argument("--cosmos-secret-key", required=True)
    parser.add_argument("--final-segment-table", help="ML completed output: catalog.schema.table")
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--wait-heartbeat-seconds", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.poll_interval_seconds <= 60:
        parser.error("--poll-interval-seconds must be between 1 and 60")
    if not args.poll_interval_seconds <= args.wait_heartbeat_seconds <= 60:
        parser.error("--wait-heartbeat-seconds must be between poll interval and 60")
    args.gold_path = storage.target_arg(args, "gold")
    args.queue_path = storage.target_arg(args, "queue")
    if args.input_mode == "ml" and not args.final_segment_table:
        parser.error("--final-segment-table must name the agreed ML completed-result table")
    event = json.loads(args.end_event)
    if event.get("event_type") != "trip_ended" or event.get("schema_version") != "trip-lifecycle-v1" or event.get("result_owner") != "databricks":
        raise ValueError("expected a Databricks-owned Trip end")
    from pyspark.sql import SparkSession, functions as F
    from delta.tables import DeltaTable
    from databricks.sdk.runtime import dbutils
    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    store = ProjectionStore(args.cosmos_endpoint, "canopy-db", "trips",
                            dbutils.secrets.get(args.secret_scope, args.cosmos_secret_key))
    key = (F.col("user_id") == event["user_id"]) & (F.col("trip_id") == event["trip_id"])
    try:
        # Recover from Gold if only Cosmos publishing failed. Do not rebuild a saved result.
        if storage.exists(spark, args.gold_path) and storage.read(spark, args.gold_path).where(
                key & (F.col("processing_generation") == event["processing_generation"])).limit(1).count():
            document = read_gold(spark, args.gold_path, event["trip_id"], event["user_id"])
            if args.input_mode == "ml" and document.get("is_mock"):
                raise ValueError("ML mode cannot reuse a fixed Mock result")
        elif args.input_mode == "mock":
            if not storage.test_target(args.gold_path) or not event["campaign_id"].startswith("pipeline_test_"):
                raise ValueError("Mock requires the isolated test campaign and Gold path")
            # Same explicit Mock as the existing phone tests. This is NOT real ML or measured distance.
            from finalize_trip_pipeline import ConfirmationFixtureProcessor
            trip = {k: event[k] for k in ("trip_id", "user_id", "campaign_id", "started_at", "ended_at", "processing_generation")}
            envelope = {"trip": trip, "result": ConfirmationFixtureProcessor().process_trip(trip),
                        "completed_at": datetime.now(timezone.utc).isoformat()}
            document = build_final_trip(envelope, allow_test_trip=True)
            save_gold(spark, args.gold_path, document)
        else:
            # 완료 결과 테이블의 접근 권한과 구조를 먼저 확인
            print(json.dumps({"trip_id": event["trip_id"], "stage": "checking_final_segments",
                              "final_segment_table": args.final_segment_table}), flush=True)
            # 실제 조회는 아래 poll에서 수행. 권한 오류를 대기로 숨기지 않고 전달
            fields = ["user_id", "trip_id", "processing_generation", "event_id", "campaign_id", "started_at",
                      "ended_at", "expected_last_sequence", "result_owner"]
            schema = "user_id string, trip_id string, processing_generation long, event_id string, campaign_id string, started_at timestamp, ended_at timestamp, expected_last_sequence long, result_owner string"
            values = {**event, **{k: datetime.fromisoformat(event[k].replace("Z", "+00:00")) for k in ("started_at", "ended_at")}}
            ends = spark.createDataFrame([tuple(values[k] for k in fields)], schema)
            register(spark, ends, args.queue_path, datetime.now(timezone.utc))
            # 저장 대상 유형 확인은 한 번만 수행. 데이터는 각 조회에서 최신 스냅샷 사용
            queue_target = storage.delta(spark, args.queue_path)
            while True:
                now = datetime.now(timezone.utc)
                # 조회 빈도가 높아져도 기존 10분 제한시간 유지. 대기열 쓰기는 별도 주기로 제한
                poll(spark, args.queue_path, args.final_segment_table, now, event=event,
                     max_attempts=None, poll_interval_seconds=args.poll_interval_seconds,
                     heartbeat_seconds=args.wait_heartbeat_seconds, queue_target=queue_target)
                wait = storage.read(spark, args.queue_path).where(
                    key & (F.col("processing_generation") == event["processing_generation"])).first()
                if wait.status == "ready":
                    document = build_final_trip(json.loads(wait.envelope_json), lifecycle=event)
                    save_gold(spark, args.gold_path, document)
                    print(json.dumps({"trip_id": event["trip_id"], "stage": "gold_saved",
                                      "observed_at": datetime.now(timezone.utc).isoformat()}), flush=True)
                    break
                if wait.status in ("timed_out", "failed", "ignored"):
                    if wait.status != "ignored":
                        publish_wait_failure(store, wait.asDict())
                    print(json.dumps({"trip_id": event["trip_id"], "status": wait.status, "reason": wait.reason}))
                    return
                time.sleep(args.poll_interval_seconds)
        status = publish_cosmos(store, document)
        print(json.dumps({"trip_id": event["trip_id"], "user_id": event["user_id"], "status": status,
                          "observed_at": datetime.now(timezone.utc).isoformat(),
                          "is_mock": document["is_mock"], "gold_path": args.gold_path}))
    except Exception:
        publish_wait_failure(store, {**event, "status": "failed", "reason": "downstream_execution_failed"})
        raise


if __name__ == "__main__":
    main()
