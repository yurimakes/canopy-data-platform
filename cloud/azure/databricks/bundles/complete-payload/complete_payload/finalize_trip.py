"""Assemble one sealed mode-detection trip into a durable complete payload."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import yaml
from pyspark.sql import SparkSession, functions as F


EARTH_RADIUS_M = 6_371_008.8


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--silver-schema", required=True)
    p.add_argument("--gps-table", required=True)
    p.add_argument("--mode-results-schema", required=True)
    p.add_argument("--mode-results-table", required=True)
    p.add_argument("--output-schema", required=True)
    p.add_argument("--output-table", required=True)
    p.add_argument("--carbon-policy", type=Path, required=True)
    p.add_argument("--trip-id", required=True)
    return p.parse_args()


def iso(value) -> str:
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def haversine_m(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(
        radians, (a["lat"], a["lon"], b["lat"], b["lon"])
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(h)))


def load_policy(path: Path) -> dict:
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {
        "policy_version", "factor_version", "supported_modes",
        "distance", "output", "factors",
    }
    missing = required - set(policy)
    if missing:
        raise ValueError(f"carbon policy missing keys: {sorted(missing)}")
    return policy


def segment_distances(points: list[dict], segments: list[dict]) -> list[float]:
    if len(points) < 2:
        return [0.0] * len(segments)

    ordered = sorted(points, key=lambda p: (p["event_time"], p["sequence"]))
    distances = [0.0] * len(segments)

    # Assign each GPS leg exactly once by its ending timestamp. A leg ending on a
    # mode boundary belongs to the segment that closes at that boundary.
    for previous, current in zip(ordered, ordered[1:]):
        leg_end = current["event_time"]
        index = next(
            (
                i
                for i, segment in enumerate(segments)
                if segment["start_time"] < leg_end <= segment["end_time"]
            ),
            None,
        )
        if index is None and leg_end == segments[0]["start_time"]:
            index = 0
        if index is not None:
            distances[index] += haversine_m(previous, current)

    return distances


def build_payload(mode_row: dict, points: list[dict], policy: dict) -> dict:
    raw_segments = [dict(s) for s in mode_row["segments"]]
    if not raw_segments:
        raise ValueError("sealed mode result contains no segments")

    distances = segment_distances(points, raw_segments)
    supported = set(policy["supported_modes"])
    factors = policy["factors"]
    meters_per_km = float(policy["distance"]["meters_per_km"])
    decimals = int(policy["output"]["storage_decimals"])

    segments = []
    total_carbon = 0.0
    total_distance = 0.0

    for index, (source, distance_m) in enumerate(zip(raw_segments, distances), start=1):
        mode = str(source["mode"]).lower()
        if mode not in supported:
            raise ValueError(f"unsupported carbon mode: {mode}")
        factor = float(factors[mode]["value"])
        carbon_kg = (distance_m / meters_per_km) * factor
        total_distance += distance_m
        total_carbon += carbon_kg
        segments.append(
            {
                "segment_id": f"{mode_row['trip_id']}:segment:{index}",
                "mode": mode,
                "model_prediction": mode,
                "start_time": iso(source["start_time"]),
                "end_time": iso(source["end_time"]),
                "distance_m": round(distance_m, 6),
                "confidence": source["confidence"],
                "prediction_count": int(source["prediction_count"]),
                "carbon_kg": carbon_kg,
            }
        )

    completed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "id": mode_row["trip_id"],
        "type": "trip",
        "trip_id": mode_row["trip_id"],
        "user_id": mode_row["user_id"],
        "campaign_id": mode_row["campaign_id"],
        "status": "ready",
        "started_at": iso(mode_row["started_at"]),
        "ended_at": iso(mode_row["ended_at"]),
        "updated_at": completed_at,
        "processing_generation": int(mode_row["processing_generation"]),
        "expected_last_sequence": int(mode_row["expected_last_sequence"]),
        "segments": segments,
        "model": {
            "name": mode_row["model_name"],
            "version": mode_row["model_version"],
            "feature_version": mode_row["feature_version"],
        },
        "carbon": {
            "kg_co2e": round(total_carbon, decimals),
            "policy_version": str(policy["policy_version"]),
            "factor_version": str(policy["factor_version"]),
            "unit": str(policy["output"]["emission_unit"]),
            "mode_source": "model_prediction",
            "user_confirmation_applied": False,
        },
        "total_distance_m": round(total_distance, 6),
        "sealed_at": iso(mode_row["sealed_at"]),
    }
    payload["finalization_hash"] = hashlib.sha256(
        canonical(payload).encode("utf-8")
    ).hexdigest()
    return payload


def save(spark: SparkSession, table_name: str, payload: dict) -> None:
    from delta.tables import DeltaTable

    row = {
        "trip_id": payload["trip_id"],
        "user_id": payload["user_id"],
        "campaign_id": payload["campaign_id"],
        "status": payload["status"],
        "started_at": payload["started_at"],
        "ended_at": payload["ended_at"],
        "updated_at": payload["updated_at"],
        "processing_generation": payload["processing_generation"],
        "finalization_hash": payload["finalization_hash"],
        "total_distance_m": payload["total_distance_m"],
        "carbon_kg_co2e": payload["carbon"]["kg_co2e"],
        "document_json": canonical(payload),
    }
    frame = spark.createDataFrame([row])

    if not spark.catalog.tableExists(table_name):
        frame.limit(0).write.format("delta").saveAsTable(table_name)

    table = DeltaTable.forName(spark, table_name)
    (
        table.alias("t")
        .merge(
            frame.alias("s"),
            "t.trip_id = s.trip_id AND t.user_id = s.user_id",
        )
        .whenMatchedUpdateAll(
            condition="s.processing_generation > t.processing_generation"
        )
        .whenNotMatchedInsertAll()
        .execute()
    )


def main() -> None:
    args = parse_args()
    if not args.trip_id.strip():
        raise ValueError("trip_id is required")

    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    gps_name = f"{args.catalog}.{args.silver_schema}.{args.gps_table}"
    mode_name = (
        f"{args.catalog}.{args.mode_results_schema}.{args.mode_results_table}"
    )
    output_name = f"{args.catalog}.{args.output_schema}.{args.output_table}"

    rows = (
        spark.table(mode_name)
        .where(F.col("trip_id") == args.trip_id)
        .orderBy(F.col("processing_generation").desc(), F.col("sealed_at").desc())
        .limit(1)
        .collect()
    )
    if not rows:
        raise ValueError(f"sealed mode result not found for trip_id={args.trip_id}")
    mode_row = rows[0].asDict(recursive=True)

    points = [
        row.asDict(recursive=True)
        for row in (
            spark.table(gps_name)
            .where(F.col("trip_id") == args.trip_id)
            .where(F.col("sequence") <= int(mode_row["expected_last_sequence"]))
            .select("sequence", "event_time", "lat", "lon")
            .orderBy("sequence")
            .collect()
        )
    ]

    expected = int(mode_row["expected_last_sequence"])
    sequences = [int(point["sequence"]) for point in points]
    if sequences != list(range(1, expected + 1)):
        raise ValueError(
            f"GPS sequence incomplete: expected 1..{expected}, got {len(points)} rows"
        )

    policy = load_policy(args.carbon_policy)
    payload = build_payload(mode_row, points, policy)
    save(spark, output_name, payload)

    print(
        "COMPLETE_PAYLOAD_REPORT",
        canonical(
            {
                "trip_id": payload["trip_id"],
                "status": "PASS",
                "segment_count": len(payload["segments"]),
                "total_distance_m": payload["total_distance_m"],
                "carbon_kg_co2e": payload["carbon"]["kg_co2e"],
                "finalization_hash": payload["finalization_hash"],
                "output_table": output_name,
            }
        ),
    )


if __name__ == "__main__":
    main()
