"""Materialize one dedicated test Reward Ledger partition into canonical Gold.

Validation scope:
- READ authoritative paid/adjusted rows from the existing dev Cosmos rewards container.
- WRITE only the dedicated pipeline_test_weekly_* campaign/week partition.
- WRITE canonical Gold reward_ledger_history.
- Re-sync the same partition twice to verify idempotency.
- DO NOT calculate new rewards or change reward policy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


CAMPAIGN = "pipeline_test_weekly_20260918"
WEEK = "2026-W38"

EXPECTED_ROW_COUNT = 3
EXPECTED_STATUS_COUNTS = {"paid": 2, "adjusted": 1}
EXPECTED_TOTAL_POINTS = 180.0


def repo_root() -> Path:
    candidates = []
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parent)
    candidates.append(Path.cwd().resolve())

    for start in candidates:
        for path in (start, *start.parents):
            if (
                path
                / "cloud"
                / "azure"
                / "pipelines"
                / "databricks"
                / "reward_ledger.py"
            ).exists():
                return path

    raise RuntimeError(
        "Repository root not found. "
        "Run from the canopy-data-platform Databricks Git Folder."
    )


def _existing_cosmos_config(root: Path) -> tuple[str, str, str]:
    """Reuse the team's existing Cosmos endpoint/secret configuration."""

    config_path = (
        root
        / "cloud"
        / "azure"
        / "pipelines"
        / "weekly_analysis"
        / "sync_campaign_membership.job.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))

    params = config["tasks"][0]["spark_python_task"]["parameters"]

    def get_arg(name: str) -> str:
        index = params.index(name)
        return params[index + 1]

    return (
        get_arg("--endpoint"),
        get_arg("--secret-scope"),
        get_arg("--secret-key"),
    )


def _verify_partition(spark, path: str) -> dict:
    from pyspark.sql import functions as F

    df = (
        spark.read.format("delta")
        .load(path)
        .where(
            (F.col("campaign_id") == CAMPAIGN)
            & (F.col("week_label") == WEEK)
        )
    )

    row_count = df.count()
    status_counts = {
        row["status"]: int(row["count"])
        for row in df.groupBy("status").count().collect()
    }
    total_points = df.agg(
        F.sum(F.col("points").cast("double")).alias("total_points")
    ).first()["total_points"]
    reward_ids = [
        row["reward_id"]
        for row in df.select("reward_id").collect()
    ]

    assert row_count == EXPECTED_ROW_COUNT, row_count
    assert status_counts == EXPECTED_STATUS_COUNTS, status_counts
    assert float(total_points) == EXPECTED_TOTAL_POINTS, total_points
    assert len(reward_ids) == len(set(reward_ids)), reward_ids

    return {
        "row_count": row_count,
        "status_counts": status_counts,
        "total_points": float(total_points),
    }


def main() -> None:
    if not CAMPAIGN.startswith("pipeline_test_weekly_"):
        raise ValueError(
            "Canonical validation may write only a dedicated pipeline_test_weekly_* campaign."
        )

    from azure.cosmos import CosmosClient
    from databricks.sdk.runtime import dbutils
    from pyspark.sql import SparkSession

    root = repo_root()
    module_dir = root / "cloud" / "azure" / "pipelines" / "databricks"

    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    import reward_ledger

    endpoint, secret_scope, secret_key = _existing_cosmos_config(root)
    credential = dbutils.secrets.get(
        scope=secret_scope,
        key=secret_key,
    )

    container = (
        CosmosClient(endpoint, credential=credential)
        .get_database_client(reward_ledger.COSMOS_DATABASE)
        .get_container_client(reward_ledger.COSMOS_REWARD_LEDGER_CONTAINER)
    )

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    target = reward_ledger.GOLD_REWARD_LEDGER_HISTORY_PATH

    first_count = reward_ledger.sync_ledger_history_from_cosmos(
        spark,
        container,
        CAMPAIGN,
        WEEK,
        target=target,
    )
    first = _verify_partition(spark, target)

    second_count = reward_ledger.sync_ledger_history_from_cosmos(
        spark,
        container,
        CAMPAIGN,
        WEEK,
        target=target,
    )
    second = _verify_partition(spark, target)

    assert first_count == EXPECTED_ROW_COUNT, first_count
    assert second_count == EXPECTED_ROW_COUNT, second_count
    assert first == second, (first, second)

    print(
        json.dumps(
            {
                "status": "REWARD_LEDGER_CANONICAL_GOLD_VALIDATION_PASSED",
                "campaign_id": CAMPAIGN,
                "week": WEEK,
                "first": first,
                "second": second,
                "canonical_gold_written": True,
                "reward_calculation_performed": False,
                "reward_policy_changed": False,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
