"""Validate actual Cosmos Reward Ledger -> sandbox Delta -> Ranking.

Validation scope:
- READ actual dev Cosmos rewards for the dedicated weekly test campaign.
- WRITE only dbw_canopy_dev.sandbox.reward_ledger_history.
- RUN the existing build_ranking transform.
- DO NOT write canonical Reward Ledger Gold.
- DO NOT write Ranking Gold.
- DO NOT publish ranking-snapshots to Cosmos.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


CAMPAIGN = "pipeline_test_weekly_20260918"
WEEK = "2026-W38"

SANDBOX_TARGET = "table:dbw_canopy_dev.sandbox.reward_ledger_history"
SANDBOX_TABLE = "dbw_canopy_dev.sandbox.reward_ledger_history"

MEMBERSHIP_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/"
    "curated/campaign_membership_raw/"
)


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


def main() -> None:
    if not CAMPAIGN.startswith("pipeline_test_weekly_"):
        raise ValueError("Only the dedicated weekly test campaign is allowed.")

    # Databricks-only imports.
    from azure.cosmos import CosmosClient
    from databricks.sdk.runtime import dbutils
    from pyspark.sql import SparkSession, functions as F
    import yaml

    root = repo_root()

    module_dir = (
        root
        / "cloud"
        / "azure"
        / "pipelines"
        / "databricks"
    )

    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    import reward_ledger
    from build_ranking import build_ranking

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    # --------------------------------------------------------------
    # Existing team Cosmos configuration.
    # Do not print the secret.
    # --------------------------------------------------------------
    job_file = (
        root
        / "cloud"
        / "azure"
        / "pipelines"
        / "weekly_analysis"
        / "sync_campaign_membership.job.json"
    )

    job_config = json.loads(
        job_file.read_text(encoding="utf-8")
    )

    params = (
        job_config["tasks"][0]
        ["spark_python_task"]
        ["parameters"]
    )

    def get_arg(name: str) -> str:
        index = params.index(name)
        return params[index + 1]

    endpoint = get_arg("--endpoint")
    secret_scope = get_arg("--secret-scope")
    secret_key = get_arg("--secret-key")

    credential = dbutils.secrets.get(
        scope=secret_scope,
        key=secret_key,
    )

    reward_container = (
        CosmosClient(endpoint, credential=credential)
        .get_database_client("canopy-db")
        .get_container_client("rewards")
    )

    # --------------------------------------------------------------
    # 1. Actual Cosmos -> sandbox Reward Ledger Delta
    # --------------------------------------------------------------
    synced_count = reward_ledger.sync_ledger_history_from_cosmos(
        spark,
        reward_container,
        CAMPAIGN,
        WEEK,
        target=SANDBOX_TARGET,
    )

    ledger_df = (
        spark.table(SANDBOX_TABLE)
        .where(
            (F.col("campaign_id") == CAMPAIGN)
            & (F.col("week_label") == WEEK)
        )
    )

    ledger_rows = [
        row.asDict(recursive=True)
        for row in ledger_df.orderBy("reward_id").collect()
    ]

    status_counts = {
        row["status"]: row["count"]
        for row in ledger_df.groupBy("status").count().collect()
    }

    total_points = (
        ledger_df
        .agg(F.sum("points").alias("total_points"))
        .first()["total_points"]
    )

    assert synced_count == 3, synced_count
    assert len(ledger_rows) == 3, ledger_rows
    assert status_counts == {
        "paid": 2,
        "adjusted": 1,
    }, status_counts
    assert float(total_points) == 180.0, total_points

    # --------------------------------------------------------------
    # 2. Existing campaign membership
    # --------------------------------------------------------------
    membership_df = (
        spark.read.format("delta")
        .load(MEMBERSHIP_PATH)
        .where(F.col("campaign_id") == CAMPAIGN)
    )

    membership_ids = {
        row["user_id"]
        for row in membership_df.select("user_id").distinct().collect()
    }

    expected_u01 = f"{CAMPAIGN}_u01"
    expected_u02 = f"{CAMPAIGN}_u02"

    missing_memberships = {
        expected_u01,
        expected_u02,
    } - membership_ids

    if missing_memberships:
        raise AssertionError(
            f"Ranking test membership missing: "
            f"{sorted(missing_memberships)}"
        )

    # --------------------------------------------------------------
    # 3. Existing Ranking policy + existing build_ranking()
    # --------------------------------------------------------------
    policy_path = module_dir / "ranking_policy.yaml"

    policy = yaml.safe_load(
        policy_path.read_text(encoding="utf-8")
    )

    personal_result, department_result = build_ranking(
        ledger_df,
        membership_df,
        policy,
    )

    personal_rows = [
        row.asDict(recursive=True)
        for row in personal_result.orderBy("rank").collect()
    ]

    department_rows = [
        row.asDict(recursive=True)
        for row in department_result.orderBy("rank").collect()
    ]

    scores = {
        row["user_id"]: {
            "score": float(row["score"]),
            "rank": int(row["rank"]),
        }
        for row in personal_rows
    }

    # Cosmos ledger:
    # u01 = +120 paid -20 adjusted = 100
    # u02 = +80 paid = 80
    assert scores.get(expected_u01) == {
        "score": 100.0,
        "rank": 1,
    }, scores

    assert scores.get(expected_u02) == {
        "score": 80.0,
        "rank": 2,
    }, scores

    print(
        json.dumps(
            {
                "status": "REWARD_RANKING_RUNTIME_VALIDATION_PASSED",
                "campaign_id": CAMPAIGN,
                "week": WEEK,
                "cosmos_reward_rows_synced": synced_count,
                "ledger_row_count": len(ledger_rows),
                "ledger_status_counts": status_counts,
                "ledger_total_points": float(total_points),
                "membership_row_count": len(membership_ids),
                "personal_ranking": [
                    {
                        "user_id": row["user_id"],
                        "score": float(row["score"]),
                        "rank": int(row["rank"]),
                    }
                    for row in personal_rows
                ],
                "department_ranking_row_count": len(department_rows),
                "canonical_reward_gold_written": False,
                "ranking_gold_written": False,
                "ranking_cosmos_published": False,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()