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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--end-event", required=True)
    parser.add_argument("--input-mode", choices=("mock", "ml"), required=True)
    parser.add_argument("--gold-path", required=True)
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--cosmos-endpoint", required=True)
    parser.add_argument("--secret-scope", required=True)
    parser.add_argument("--cosmos-secret-key", required=True)
    parser.add_argument("--gps-table", default="dbw_canopy_dev.silver.gps_features")
    parser.add_argument("--prediction-table", default="dbw_canopy_dev.gold.mode_segment_predictions")
    args = parser.parse_args()
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
        if DeltaTable.isDeltaTable(spark, args.gold_path) and spark.read.format("delta").load(args.gold_path).where(
                key & (F.col("processing_generation") == event["processing_generation"])).limit(1).count():
            document = read_gold(spark, args.gold_path, event["trip_id"], event["user_id"])
            if args.input_mode == "ml" and document.get("is_mock"):
                raise ValueError("ML mode cannot reuse a fixed Mock result")
        elif args.input_mode == "mock":
            if "/pipeline_test/" not in args.gold_path or not event["campaign_id"].startswith("pipeline_test_"):
                raise ValueError("Mock requires the isolated test campaign and Gold path")
            # Same explicit Mock as the existing phone tests. This is NOT real ML or measured distance.
            envelope = {"provider": "mock", "trip": {**event, "status": "processing"},
                        "completed_at": datetime.now(timezone.utc).isoformat()}
            document = build_final_trip(envelope, allow_test_trip=True)
            save_gold(spark, args.gold_path, document)
        else:
            # Fail before entering the wait loop when the Job cannot read its inputs.
            # Missing permissions are not late ML predictions.
            print(json.dumps({"trip_id": event["trip_id"], "stage": "checking_ml_inputs",
                              "gps_table": args.gps_table, "prediction_table": args.prediction_table}), flush=True)
            spark.table(args.gps_table).select("user_id", "trip_id", "sequence", "event_time", "distance_m", "transition_valid").limit(1).collect()
            spark.table(args.prediction_table).select("user_id", "trip_id", "segment_id", "strong_mode", "inference_status").limit(1).collect()
            fields = ["user_id", "trip_id", "processing_generation", "event_id", "campaign_id", "started_at",
                      "ended_at", "expected_last_sequence", "result_owner"]
            schema = "user_id string, trip_id string, processing_generation long, event_id string, campaign_id string, started_at timestamp, ended_at timestamp, expected_last_sequence long, result_owner string"
            values = {**event, **{k: datetime.fromisoformat(event[k].replace("Z", "+00:00")) for k in ("started_at", "ended_at")}}
            ends = spark.createDataFrame([tuple(values[k] for k in fields)], schema)
            register(spark, ends, args.queue_path, datetime.now(timezone.utc))
            while True:
                now = datetime.now(timezone.utc)
                poll(spark, args.queue_path, args.gps_table, args.prediction_table, now)
                wait = spark.read.format("delta").load(args.queue_path).where(
                    key & (F.col("processing_generation") == event["processing_generation"])).first()
                if wait.status == "ready":
                    document = build_final_trip(json.loads(wait.envelope_json))
                    save_gold(spark, args.gold_path, document)
                    break
                if wait.status in ("timed_out", "failed", "ignored"):
                    if wait.status != "ignored":
                        publish_wait_failure(store, wait.asDict())
                    print(json.dumps({"trip_id": event["trip_id"], "status": wait.status, "reason": wait.reason}))
                    return
                due = wait.next_check_at.replace(tzinfo=timezone.utc)
                time.sleep(max(1, min(60, (due - datetime.now(timezone.utc)).total_seconds())))
        status = publish_cosmos(store, document)
        print(json.dumps({"trip_id": event["trip_id"], "user_id": event["user_id"], "status": status,
                          "is_mock": document["is_mock"], "gold_path": args.gold_path}))
    except Exception:
        publish_wait_failure(store, {**event, "status": "failed", "reason": "downstream_execution_failed"})
        raise


if __name__ == "__main__":
    main()
