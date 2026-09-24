"""Continuously project durable final Gold payloads into Cosmos DB."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from azure.core import MatchConditions
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import (
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)
from delta.tables import DeltaTable
from pyspark.sql import SparkSession, functions as F

from cosmos_projection.projection import merge_projection


STATUS_SCHEMA = """
trip_id STRING NOT NULL,
user_id STRING NOT NULL,
processing_generation BIGINT NOT NULL,
finalization_hash STRING NOT NULL,
status STRING NOT NULL,
attempt_count BIGINT NOT NULL,
last_attempt_at TIMESTAMP NOT NULL,
projected_at TIMESTAMP,
last_error STRING,
cosmos_etag STRING
"""


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--gold-table", required=True)
    p.add_argument("--status-table", required=True)
    p.add_argument("--cosmos-endpoint", required=True)
    p.add_argument("--cosmos-database", required=True)
    p.add_argument("--cosmos-container", required=True)
    p.add_argument("--cosmos-secret-scope", required=True)
    p.add_argument("--cosmos-key", required=True)
    p.add_argument("--poll-seconds", type=float, default=0.5)
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--allow-missing-create", choices=("true", "false"), default="false")
    return p.parse_args()


def now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_status_table(spark: SparkSession, table_name: str) -> None:
    if spark.catalog.tableExists(table_name):
        return
    spark.sql(f"CREATE TABLE {table_name} ({STATUS_SCHEMA}) USING DELTA")


def candidates(spark: SparkSession, gold_table: str, status_table: str, limit: int):
    terminal = (
        spark.table(status_table)
        .where(F.col("status").isin("published", "already_published", "stale"))
        .select("trip_id", "user_id", "processing_generation", "finalization_hash")
    )
    return (
        spark.table(gold_table)
        .alias("g")
        .join(
            terminal.alias("s"),
            (
                (F.col("g.trip_id") == F.col("s.trip_id"))
                & (F.col("g.user_id") == F.col("s.user_id"))
                & (F.col("g.processing_generation") == F.col("s.processing_generation"))
                & (F.col("g.finalization_hash") == F.col("s.finalization_hash"))
            ),
            "left_anti",
        )
        .orderBy(F.col("g.sealed_at").asc())
        .limit(limit)
        .collect()
    )


def status_attempts(spark: SparkSession, status_table: str, trip_id: str, user_id: str, generation: int) -> int:
    rows = (
        spark.table(status_table)
        .where(
            (F.col("trip_id") == trip_id)
            & (F.col("user_id") == user_id)
            & (F.col("processing_generation") == generation)
        )
        .select("attempt_count")
        .limit(1)
        .collect()
    )
    return int(rows[0]["attempt_count"]) if rows else 0


def save_status(
    spark: SparkSession,
    table_name: str,
    *,
    trip_id: str,
    user_id: str,
    generation: int,
    finalization_hash: str,
    status: str,
    attempt_count: int,
    projected_at: datetime | None,
    last_error: str | None,
    cosmos_etag: str | None,
) -> None:
    frame = spark.createDataFrame(
        [(
            trip_id,
            user_id,
            generation,
            finalization_hash,
            status,
            attempt_count,
            now_naive(),
            projected_at,
            last_error,
            cosmos_etag,
        )],
        schema=STATUS_SCHEMA,
    )
    (
        DeltaTable.forName(spark, table_name)
        .alias("t")
        .merge(
            frame.alias("s"),
            "t.trip_id=s.trip_id AND t.user_id=s.user_id "
            "AND t.processing_generation=s.processing_generation",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


def read_current(container, trip_id: str, user_id: str):
    try:
        return container.read_item(item=trip_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return None


def project(container, payload: dict, allow_missing_create: bool):
    for _ in range(5):
        current = read_current(container, payload["trip_id"], payload["user_id"])
        action, body = merge_projection(
            current, payload, allow_missing_create=allow_missing_create
        )
        if action in ("stale", "already_published"):
            saved = current
        elif action == "create":
            try:
                saved = container.create_item(body=body)
            except CosmosResourceExistsError:
                continue
        else:
            try:
                saved = container.replace_item(
                    item=current["id"],
                    body=body,
                    etag=current["_etag"],
                    match_condition=MatchConditions.IfNotModified,
                )
            except CosmosHttpResponseError as exc:
                if exc.status_code in (409, 412):
                    continue
                raise

        verified = read_current(container, payload["trip_id"], payload["user_id"])
        if action == "stale":
            return action, verified
        if not verified or verified.get("finalization_hash") != payload["finalization_hash"]:
            raise RuntimeError("Cosmos read-back finalization_hash mismatch")
        return action, verified
    raise RuntimeError("Cosmos projection conflicted repeatedly")


def main() -> None:
    a = args()
    if a.poll_seconds <= 0 or a.batch_size < 1:
        raise ValueError("poll-seconds and batch-size must be positive")

    from databricks.sdk.runtime import dbutils

    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    ensure_status_table(spark, a.status_table)

    credential = dbutils.secrets.get(a.cosmos_secret_scope, a.cosmos_key)
    client = CosmosClient(a.cosmos_endpoint, credential=credential)
    container = (
        client.get_database_client(a.cosmos_database)
        .get_container_client(a.cosmos_container)
    )
    if container.read()["partitionKey"]["paths"] != ["/user_id"]:
        raise ValueError("Cosmos trips container must use /user_id partition key")

    allow_missing_create = a.allow_missing_create == "true"
    print(
        "COSMOS_PROJECTION_READY",
        json.dumps(
            {
                "gold_table": a.gold_table,
                "status_table": a.status_table,
                "allow_missing_create": allow_missing_create,
            }
        ),
        flush=True,
    )

    while True:
        rows = candidates(spark, a.gold_table, a.status_table, a.batch_size)
        if not rows:
            time.sleep(a.poll_seconds)
            continue

        for row in rows:
            payload = json.loads(row["document_json"])
            generation = int(row["processing_generation"])
            attempt = status_attempts(
                spark, a.status_table, row["trip_id"], row["user_id"], generation
            ) + 1
            try:
                action, saved = project(container, payload, allow_missing_create)
                projected_at = now_naive()
                terminal_status = (
                    "published" if action in ("create", "replace") else action
                )
                save_status(
                    spark,
                    a.status_table,
                    trip_id=row["trip_id"],
                    user_id=row["user_id"],
                    generation=generation,
                    finalization_hash=row["finalization_hash"],
                    status=terminal_status,
                    attempt_count=attempt,
                    projected_at=projected_at,
                    last_error=None,
                    cosmos_etag=None if saved is None else saved.get("_etag"),
                )
                print(
                    "COSMOS_PROJECTION_SUCCESS",
                    json.dumps(
                        {
                            "trip_id": row["trip_id"],
                            "processing_generation": generation,
                            "action": action,
                            "projected_at": projected_at.isoformat(),
                        }
                    ),
                    flush=True,
                )
            except Exception as exc:
                save_status(
                    spark,
                    a.status_table,
                    trip_id=row["trip_id"],
                    user_id=row["user_id"],
                    generation=generation,
                    finalization_hash=row["finalization_hash"],
                    status="failed",
                    attempt_count=attempt,
                    projected_at=None,
                    last_error=f"{type(exc).__name__}: {str(exc)[:1200]}",
                    cosmos_etag=None,
                )
                print(
                    "COSMOS_PROJECTION_FAILURE",
                    json.dumps(
                        {
                            "trip_id": row["trip_id"],
                            "processing_generation": generation,
                            "attempt": attempt,
                            "error": f"{type(exc).__name__}: {str(exc)[:1200]}",
                        }
                    ),
                    flush=True,
                )
                time.sleep(min(60.0, 2.0 ** min(attempt, 5)))


if __name__ == "__main__":
    main()
