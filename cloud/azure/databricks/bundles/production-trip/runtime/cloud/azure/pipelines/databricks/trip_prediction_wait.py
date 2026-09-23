"""종료 이벤트와 ML Final Segment 완료 결과 연결. ML 테이블은 읽기만 수행."""
import json
from datetime import datetime, timedelta, timezone
from finalize_trip_pipeline import build_final_trip, canonical
from services.trip_processor import ProcessingError
import trip_delta_store as storage

KEYS = ["user_id", "trip_id", "processing_generation"]


def resolve(ended, candidates):
    """동일 사용자, Trip, 처리 차수 결과만 선택. 거리 재계산과 구간 생성 제외."""
    if ended["result_owner"] != "databricks":
        return "functions_owned", None
    if ended["expected_last_sequence"] <= 0:
        return "no_gps", None
    matching = [item for item in candidates if all(
        item.get("trip", {}).get(k) == ended[k] for k in KEYS)]
    unique = {canonical(item): item for item in matching}
    if not unique:
        return "waiting_for_final_segments", None
    if len(unique) != 1:
        return "conflicting_final_segments", None
    envelope = next(iter(unique.values()))
    trip = envelope["trip"]
    if trip.get("campaign_id") != ended["campaign_id"]:
        return "lifecycle_context_mismatch", None
    # 공통 검증과 탄소 계산을 통과한 완성 결과만 대기열에 고정
    build_final_trip(envelope)
    return "ready", canonical(envelope)


def advance(wait, reason, envelope_json, now, max_attempts=12):
    """최대 대기시간과 시도 횟수 적용. 만료 후에는 명시적 재시도 필요."""
    attempts = wait["attempts"] + 1
    deadline = wait["deadline_at"]
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if reason == "functions_owned":
        status = "ignored"
    elif reason in ("no_gps", "conflicting_final_segments", "lifecycle_context_mismatch", "invalid_final_segments"):
        status = "failed"
    elif now >= deadline or (attempts >= max_attempts and reason != "ready"):
        status = "timed_out"
    else:
        status = "ready" if reason == "ready" else "waiting"
    return {"attempts": attempts, "status": status, "reason": reason,
            "next_check_at": now + timedelta(seconds=min(60, 10 * 2 ** min(attempts - 1, 3))),
            "checked_at": now, "envelope_json": envelope_json if status == "ready" else None}


def register(spark, ends, queue_path, now, timeout_seconds=600):
    """First receipt starts the deadline; replay must never reset it."""
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F, Window
    instant = F.lit(now).cast("timestamp")
    fields = [*KEYS, "event_id", "campaign_id", "started_at", "ended_at", "expected_last_sequence", "result_owner"]
    unique = ends.select(*fields).dropDuplicates()
    grouped = Window.partitionBy(*KEYS)
    unique = unique.withColumn("variants", F.count("event_id").over(grouped)).withColumn(
        "pick", F.row_number().over(grouped.orderBy(F.to_json(F.struct(*fields))))).where("pick=1")
    valid = (F.col("expected_last_sequence").between(0, 10000000)) & (F.col("processing_generation") >= 1) & (
        F.col("ended_at") >= F.col("started_at")) & F.col("result_owner").isin("functions", "databricks")
    for key in ("user_id", "trip_id", "event_id", "campaign_id"):
        valid = valid & (F.length(F.trim(F.col(key))) > 0)
    rows = unique.withColumn("status", F.when((F.col("variants") != 1) | ~F.coalesce(valid, F.lit(False)), "failed").otherwise("waiting"))
    rows = rows.withColumn("reason", F.when(F.col("variants") != 1, "conflicting_end_events")
                           .when(F.col("status") == "failed", "invalid_end_event").otherwise("not_checked")).drop("variants", "pick").withColumn(
        "attempts", F.lit(0)).withColumn("first_seen_at", instant).withColumn("next_check_at", instant).withColumn(
        "deadline_at", F.timestamp_micros(F.unix_micros(instant) + timeout_seconds * 1000000)).withColumn(
        "checked_at", F.lit(None).cast("timestamp")).withColumn("envelope_json", F.lit(None).cast("string")).withColumn(
        "retry_request_id", F.lit(None).cast("string"))
    storage.initialize(spark, queue_path, rows)
    target = storage.delta(spark, queue_path)
    same = F.struct(*[F.col("t."+k) for k in fields]).eqNullSafe(F.struct(*[F.col("s."+k) for k in fields]))
    target.alias("t").merge(rows.alias("s"), " AND ".join("t."+k+"=s."+k for k in KEYS)).whenMatchedUpdate(
        condition=(F.col("t.status") == "waiting") & (~same | (F.col("s.status") == "failed")),
        set={"status": F.lit("failed"), "reason": F.lit("conflicting_end_events")}).whenNotMatchedInsertAll().execute()


def normalize_table_result(row):
    """팀 테이블의 추적용 열은 유지하고, 계산 입력에 필요한 필드만 투영."""
    trip = row["trip"]
    for key in ("trip_id", "processing_generation"):
        if key in row and row[key] != trip[key]:
            raise ValueError("outer and nested " + key + " differ")
    envelope = {"trip": {k: trip[k] for k in (
        "trip_id", "user_id", "campaign_id", "started_at", "ended_at", "processing_generation")},
        "result": {"trip_id": row["result"]["trip_id"], "model_version": row["result"]["model_version"],
            "segments": [{k: segment[k] for k in (
                "segment_id", "mode", "start_time", "end_time", "distance_m", "confidence")}
                for segment in row["result"]["segments"]]}, "completed_at": row["completed_at"]}
    for key in ('data_quality','endpoint_observations'):
        if row['result'].get(key) is not None:envelope['result'][key]=row['result'][key]
    for segment in envelope["result"]["segments"]:
        if segment["mode"] in ("subway", "train"):
            segment["mode"] = "rail"
    return envelope


def read_candidates(spark, table, ended):
    """해당 Trip 처리 차수만 조회. null 신뢰도 보존, 상충 결과 최대 2건 확인."""
    from pyspark.sql import functions as F
    source = spark.table(table)
    for key in KEYS:
        source = source.where(F.col("trip." + key) == ended[key])
    rows = source.select(F.to_json(F.struct(*[F.col(c) for c in source.columns]),
        options={"ignoreNullFields": "false", "timestampFormat": "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX"}).alias("payload")).distinct().limit(2).collect()
    return [normalize_table_result(json.loads(row.payload)) for row in rows]


def poll(spark, queue_path, final_segment_table, now, max_attempts=12, event=None):
    """완성 결과 테이블만 조회. 대기열 외 ML 데이터와 GPS 원본 변경 없음."""
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    target = storage.delta(spark, queue_path)
    due = target.toDF().where((F.col("status") == "waiting") & (F.col("next_check_at") <= F.lit(now)))
    if event:
        for key in KEYS:
            due = due.where(F.col(key) == event[key])
    for row in due.toLocalIterator():
        wait = row.asDict()
        ended = {**wait, **{k: wait[k].replace(tzinfo=timezone.utc).isoformat()
                           if wait[k].tzinfo is None else wait[k].isoformat()
                           for k in ("started_at", "ended_at")}}
        # 잘못된 테이블/권한은 데이터 지연으로 숨기지 않고 호출자에게 오류 전달
        payloads = read_candidates(spark, final_segment_table, wait)
        try:
            reason, envelope = resolve(ended, payloads)
        except (ValueError, TypeError, KeyError, ProcessingError):
            reason, envelope = "invalid_final_segments", None
        changes = advance(wait, reason, envelope, now, max_attempts)
        condition = (F.col("status") == "waiting") & (F.col("attempts") == wait["attempts"]) & (
            F.col("retry_request_id").eqNullSafe(F.lit(wait["retry_request_id"])))
        for key in KEYS:
            condition = condition & (F.col(key) == wait[key])
        target.update(condition, {k: F.lit(v) for k, v in changes.items()})


def retry(spark, queue_path, user_id, trip_id, generation, request_id, now, timeout_seconds=600):
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F
    if not request_id or not request_id.strip():
        raise ValueError("retry request ID is required")
    target = storage.delta(spark, queue_path)
    condition = ((F.col("user_id") == user_id) & (F.col("trip_id") == trip_id) &
                 (F.col("processing_generation") == generation) & (F.col("status") == "timed_out") &
                 (~F.col("retry_request_id").eqNullSafe(F.lit(request_id))))
    instant = F.lit(now).cast("timestamp")
    target.update(condition, {"status": F.lit("waiting"), "reason": F.lit("manual_retry"), "attempts": F.lit(0),
        "next_check_at": instant, "deadline_at": F.timestamp_micros(F.unix_micros(instant) + timeout_seconds * 1000000),
        "retry_request_id": F.lit(request_id)})
