"""Final segments -> canonical Gold -> Cosmos projection. No ML or resource creation."""
import argparse
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import time

# Serverless script tasks execute compiled source without defining __file__.
ROOT = Path(inspect.currentframe().f_code.co_filename).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/api"))
from services.trip_carbon import finalize_result
from services.trip_processor import timestamp, validate_result
from services.mock_trip_processor import ConfirmationFixtureProcessor
from services.cosmos_service import Conflict, CosmosTripStore
import trip_delta_store as storage


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_final_trip(envelope, allow_test_trip=False, lifecycle=None):
    """The envelope supplies lifecycle context; result uses existing ProcessorResult."""
    if set(envelope) != {"trip", "result", "completed_at"}:
        raise ValueError("expected trip, result and completed_at only")
    trip = deepcopy(envelope["trip"])
    if set(trip) != {"trip_id", "user_id", "campaign_id", "started_at", "ended_at", "processing_generation"}:
        raise ValueError("invalid Final Segment Trip context fields")
    if set(envelope["result"]) != {"trip_id", "model_version", "segments"}:
        raise ValueError("invalid Final Segment result fields")
    for key in ("trip_id", "user_id", "campaign_id", "started_at", "ended_at"):
        if not isinstance(trip.get(key), str) or not trip[key].strip():
            raise ValueError("missing Trip context: " + key)
    generation = trip.get("processing_generation")
    if type(generation) is not int or generation < 1:
        raise ValueError("processing_generation must be a positive integer")
    completed_at = envelope["completed_at"]
    if timestamp(completed_at) < timestamp(trip["ended_at"]):
        raise ValueError("completed_at precedes Trip end")
    result = deepcopy(envelope["result"])
    is_mock = result.get("model_version", "").startswith("mock")
    if is_mock and not (allow_test_trip and trip["campaign_id"].startswith("pipeline_test_")):
        raise ValueError("Mock requires explicit test execution and pipeline_test_ campaign")
    validate_result(trip, result)
    # Construct owned result fields explicitly; never accept user feedback from ML.
    segments = []
    for source in result["segments"]:
        if set(source) != {"segment_id", "mode", "start_time", "end_time", "distance_m", "confidence"}:
            raise ValueError("invalid Final Segment fields")
        segment = {k: source[k] for k in ("segment_id", "mode", "start_time", "end_time", "distance_m", "confidence")}
        segment.update(model_prediction=source["mode"], confirmed_mode=None, corrected=False,
                       correction_status="none", confirmation_time=None, last_request_id=None,
                       started_at=source["start_time"], ended_at=source["end_time"],
                       duration_min=(timestamp(source["end_time"]) - timestamp(source["start_time"])).total_seconds() / 60)
        for key in ("start_name", "end_name", "route_name"):
            segment[key] = source.get(key)
        segments.append(segment)
    document = {key: trip[key] for key in ("trip_id", "user_id", "campaign_id", "started_at", "ended_at", "processing_generation")}
    document.update(id=trip["trip_id"], type="trip", status="ready", segments=segments,
                    model_version=result["model_version"], is_mock=is_mock,
                    created_at=trip.get("created_at", trip["started_at"]), updated_at=completed_at,
                    failed_step=None, error_message=None, lease_until="", process_after="")
    if lifecycle is not None:
        for key in ("trip_id", "user_id", "campaign_id", "processing_generation"):
            if lifecycle[key] != trip[key]:
                raise ValueError("lifecycle identity differs: " + key)
        if timestamp(lifecycle["ended_at"]) < timestamp(lifecycle["started_at"]):
            raise ValueError("invalid lifecycle times")
        document["lifecycle_started_at"] = lifecycle["started_at"]
        document["lifecycle_ended_at"] = lifecycle["ended_at"]
    finalize_result(document, segments, completed_at)
    # Input time is stable across retries, making same-generation replays identical.
    document["finalization_hash"] = hashlib.sha256(canonical(document).encode()).hexdigest()
    return document


def verify_document(document):
    body = {k: v for k, v in document.items() if k != "finalization_hash"}
    if hashlib.sha256(canonical(body).encode()).hexdigest() != document.get("finalization_hash"):
        raise ValueError("Gold document hash mismatch")


def gold_frame(spark, document):
    """Typed columns consumed directly by the existing Weekly code, plus full payload."""
    from pyspark.sql import functions as F
    schema = """struct<trip_id:string,user_id:string,campaign_id:string,status:string,
      started_at:string,ended_at:string,updated_at:string,is_mock:boolean,processing_generation:long,
      finalization_hash:string,segments:array<struct<segment_id:string,model_prediction:string,
      distance_m:double,carbon_kg:double>>,carbon:struct<kg_co2e:double,policy_version:string,
      factor_version:string,unit:string>>"""
    return spark.createDataFrame([(canonical(document),)], "document_json string").withColumn(
        "body", F.from_json("document_json", schema)).select("body.*", "document_json")


def save_gold(spark, path, document):
    # Different phone Trips can reach the same Delta table concurrently.
    # Retry only transaction conflicts, with the same immutable result.
    for attempt in range(5):
        try:
            return _save_gold(spark, path, document)
        except Exception as exc:
            conflict = any(code in str(exc) for code in (
                "DELTA_CONCURRENT", "DELTA_PROTOCOL_CHANGED", "DELTA_METADATA_CHANGED",
                "ConcurrentAppendException", "ProtocolChangedException", "MetadataChangedException"))
            if not conflict or attempt == 4:
                raise
            time.sleep(min(8, 2 ** attempt))


def _save_gold(spark, path, document):
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    verify_document(document)
    frame = gold_frame(spark, document)
    storage.initialize(spark, path, frame)
    if storage.exists(spark, path):
        table = storage.delta(spark, path)
        rows = table.toDF().filter((F.col("trip_id") == document["trip_id"]) &
                                  (F.col("user_id") == document["user_id"])).select(
                                      "processing_generation", "finalization_hash").collect()
        for row in rows:
            if row.processing_generation > document["processing_generation"]:
                raise ValueError("stale processing generation")
            if row.processing_generation == document["processing_generation"] and row.finalization_hash != document["finalization_hash"]:
                raise ValueError("conflicting result for the same processing generation")
        (table.alias("t").merge(frame.alias("s"), "t.trip_id = s.trip_id AND t.user_id = s.user_id")
         .whenMatchedUpdateAll(condition="s.processing_generation > t.processing_generation")
         .whenNotMatchedInsertAll().execute())
    saved = read_gold(spark, path, document["trip_id"], document["user_id"])
    if saved["finalization_hash"] != document["finalization_hash"]:
        raise ValueError("Gold write lost a concurrent update; retry from the current generation")
    return saved


def read_gold(spark, path, trip_id, user_id):
    from pyspark.sql import functions as F
    rows = storage.read(spark, path).filter(
        (F.col("trip_id") == trip_id) & (F.col("user_id") == user_id)).select("document_json").limit(2).collect()
    if len(rows) != 1:
        raise ValueError("expected exactly one canonical Gold Trip")
    document = json.loads(rows[0].document_json)
    verify_document(document)
    return document


def publish_cosmos(store, document, allow_test_create=False):
    """CAS projection only. Gold is durable before this runs. Preserve feedback."""
    verify_document(document)
    for _ in range(5):
        current = store.read(document["trip_id"], document["user_id"])
        try:
            if current is None:
                if not (allow_test_create and document["is_mock"] and document["trip_id"].startswith("pipeline_test_")):
                    raise ValueError("missing lifecycle Trip; creating production Trips is forbidden")
                store.create(deepcopy(document))
            elif current.get("finalization_hash") == document["finalization_hash"]:
                return "already_published"
            else:
                if current.get("processing_generation") != document["processing_generation"]:
                    raise ValueError("Cosmos lifecycle generation differs from Gold")
                if current.get("status") != "processing" or current.get("result_owner") != "databricks":
                    raise ValueError("Trip is not assigned to Databricks; refusing to replace another worker's result")
                for key in ("user_id", "campaign_id", "started_at", "ended_at"):
                    if (timestamp(current[key]) != timestamp(document.get("lifecycle_" + key, document[key])) if key in ("started_at", "ended_at")
                            else current.get(key) != document[key]):
                        raise ValueError("lifecycle context differs: " + key)
                merged = {**current, **document}
                merged.pop("wait_reason", None)
                merged["created_at"] = current.get("created_at", document["created_at"])
                store.replace(merged)
            saved = store.read(document["trip_id"], document["user_id"])
            if saved is None or saved.get("finalization_hash") != document["finalization_hash"]:
                raise RuntimeError("Cosmos projection read-back failed")
            return "published"
        except Conflict:
            continue
    raise RuntimeError("Cosmos projection conflicted repeatedly; retry publishing from Gold")


class ProjectionStore(CosmosTripStore):
    """Reuse the existing CAS operations with an explicitly supplied credential."""
    def __init__(self, endpoint, database, container, credential):
        from azure.cosmos import CosmosClient
        self.client = CosmosClient(endpoint, credential=credential)
        self.container = self.client.get_database_client(database).get_container_client(container)
        if self.container.read()["partitionKey"]["paths"] != ["/user_id"]:
            raise ValueError("Trip container must use /user_id")


def publish_wait_failure(store, wait):
    """Expose bounded wait failure using the existing app 'failed' status."""
    if wait["status"] not in ("timed_out", "failed"):
        raise ValueError("only a terminal wait failure can be projected")
    for _ in range(5):
        current = store.read(wait["trip_id"], wait["user_id"])
        if current is None or current.get("processing_generation") != wait["processing_generation"]:
            return "stale_wait"
        if current.get("status") == "failed" and current.get("failed_step") == "wait_for_ml":
            return "already_published"
        if current.get("status") != "processing" or current.get("result_owner") != "databricks":
            return "not_owned"
        current.update(status="failed", failed_step="wait_for_ml",
                       error_message="Final Segment results are delayed or invalid. Retry after checking the source.",
                       wait_reason=wait["reason"], lease_until="", process_after="")
        try:
            store.replace(current)
            return "published"
        except Conflict:
            continue
    raise RuntimeError("wait failure projection conflicted; retry")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("finalize", "publish", "publish-wait-failure"))
    storage.add_target(parser, "gold", required=False)
    parser.add_argument("--input", help="one JSON envelope in an accessible Workspace file")
    parser.add_argument("--ready-path", help="Delta wait queue containing a frozen ready envelope")
    parser.add_argument("--trip-id")
    parser.add_argument("--user-id")
    parser.add_argument("--allow-test-create", action="store_true")
    parser.add_argument("--cosmos-endpoint", default=os.environ.get("COSMOS_ENDPOINT"))
    parser.add_argument("--cosmos-database", default=os.environ.get("COSMOS_TRIPS_DATABASE", "canopy-db"))
    parser.add_argument("--cosmos-container", default=os.environ.get("COSMOS_TRIPS_CONTAINER", "trips"))
    parser.add_argument("--cosmos-secret-scope")
    parser.add_argument("--cosmos-secret-key")
    args = parser.parse_args()
    args.gold_path = storage.target_arg(args, "gold")
    if args.phase != "publish-wait-failure" and not args.gold_path:
        parser.error("--gold-table or --gold-path is required")
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    if args.phase == "finalize":
        if bool(args.input) == bool(args.ready_path):
            parser.error("choose exactly one of --input or --ready-path")
        if args.ready_path:
            if not args.trip_id or not args.user_id:
                parser.error("--ready-path requires --trip-id and --user-id")
            from pyspark.sql import functions as F
            rows = spark.read.format("delta").load(args.ready_path).where(
                (F.col("trip_id") == args.trip_id) & (F.col("user_id") == args.user_id)
            ).orderBy(F.col("processing_generation").desc()).select("status", "envelope_json").limit(1).collect()
            if not rows or rows[0].status != "ready" or not rows[0].envelope_json:
                raise ValueError("latest Trip generation is not ready; do not calculate carbon")
            envelope = json.loads(rows[0].envelope_json)
        else:
            envelope = json.loads(Path(args.input).read_text(encoding="utf-8"))
        document = build_final_trip(envelope, allow_test_trip=args.allow_test_create)
        if document["is_mock"] and not storage.test_target(args.gold_path):
            raise ValueError("Mock Gold requires a sandbox/pipeline_test table or pipeline_test path")
        save_gold(spark, args.gold_path, document)
        print(canonical({"trip_id": document["trip_id"], "phase": "gold_saved", "hash": document["finalization_hash"]}))
    elif args.phase in ("publish", "publish-wait-failure"):
        if not args.cosmos_endpoint:
            raise ValueError("Cosmos endpoint is required")
        if args.cosmos_secret_scope and args.cosmos_secret_key:
            from pyspark.dbutils import DBUtils
            credential = DBUtils(spark).secrets.get(args.cosmos_secret_scope, args.cosmos_secret_key)
        elif args.cosmos_secret_scope or args.cosmos_secret_key:
            raise ValueError("both Cosmos secret scope and key are required")
        else:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
        store = ProjectionStore(args.cosmos_endpoint, args.cosmos_database, args.cosmos_container, credential)
        if args.phase == "publish-wait-failure":
            if not args.ready_path or not args.trip_id or not args.user_id:
                parser.error("--ready-path, --trip-id and --user-id are required")
            from pyspark.sql import functions as F
            rows = spark.read.format("delta").load(args.ready_path).where(
                (F.col("trip_id") == args.trip_id) & (F.col("user_id") == args.user_id)
            ).orderBy(F.col("processing_generation").desc()).limit(1).collect()
            if not rows:
                raise ValueError("Trip wait record not found")
            print(publish_wait_failure(store, rows[0].asDict()))
        else:
            document = read_gold(spark, args.gold_path, args.trip_id, args.user_id)
            print(publish_cosmos(store, document, args.allow_test_create))



if __name__ == "__main__":
    main()
