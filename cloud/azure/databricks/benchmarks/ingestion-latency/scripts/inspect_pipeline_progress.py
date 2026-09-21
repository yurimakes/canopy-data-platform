"""Print recent Lakeflow flow_progress events for ingestion latency diagnosis."""

from __future__ import annotations

import argparse
import json

from pyspark.sql import SparkSession


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--pipeline-id", required=True)
    p.add_argument("--minutes", type=int, default=30)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    rows = spark.sql(
        f"""
        SELECT
          timestamp,
          origin:flow_name::STRING AS flow_name,
          origin:update_id::STRING AS update_id,
          details:flow_progress:status::STRING AS status,
          TRY_CAST(details:flow_progress:metrics:num_output_rows AS BIGINT) AS num_output_rows,
          TRY_CAST(details:flow_progress:metrics:num_output_bytes AS BIGINT) AS num_output_bytes,
          TRY_CAST(details:flow_progress:metrics:backlog_records AS BIGINT) AS backlog_records,
          TRY_CAST(details:flow_progress:metrics:backlog_bytes AS BIGINT) AS backlog_bytes,
          TRY_CAST(details:flow_progress:metrics:executor_time_ms AS BIGINT) AS executor_time_ms,
          details:flow_progress:metrics:source_metrics AS source_metrics
        FROM event_log('{args.pipeline_id}')
        WHERE event_type = 'flow_progress'
          AND timestamp >= current_timestamp() - INTERVAL {args.minutes} MINUTES
        ORDER BY timestamp, flow_name
        """
    ).collect()

    print("INGESTION_FLOW_PROGRESS_BEGIN")
    for row in rows:
        print(json.dumps(row.asDict(recursive=True), default=str))
    print("INGESTION_FLOW_PROGRESS_END")


if __name__ == "__main__":
    main()
