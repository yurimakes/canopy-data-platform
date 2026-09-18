"""Validate Reward-points Ranking -> existing Cosmos ranking container.

Test scope only:
- Existing canopy-db/ranking container
- Dedicated pipeline_test_weekly campaign only
- Existing legacy carbon-ranking documents are never modified
- No canonical Ranking Gold write
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


CAMPAIGN = "pipeline_test_weekly_20260918"
WEEK = "2026-W38"

RANKING_CONTAINER = "ranking"

SANDBOX_LEDGER_TABLE = (
    "dbw_canopy_dev.sandbox.reward_ledger_history"
)

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
                / "build_ranking.py"
            ).exists():
                return path

    raise RuntimeError("Repository root not found")


def main() -> None:
    if not CAMPAIGN.startswith("pipeline_test_weekly_"):
        raise ValueError("Test campaign required")

    import yaml
    from azure.cosmos import CosmosClient
    from azure.cosmos.exceptions import CosmosResourceNotFoundError
    from databricks.sdk.runtime import dbutils
    from pyspark.sql import SparkSession, functions as F

    root = repo_root()

    module_dir = (
        root
        / "cloud"
        / "azure"
        / "pipelines"
        / "databricks"
    )

    sys.path.insert(0, str(module_dir))

    from build_ranking import build_ranking

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    # Existing team Cosmos configuration
    job_file = (
        root
        / "cloud"
        / "azure"
        / "pipelines"
        / "weekly_analysis"
        / "sync_campaign_membership.job.json"
    )

    config = json.loads(
        job_file.read_text(encoding="utf-8")
    )

    params = (
        config["tasks"][0]
        ["spark_python_task"]
        ["parameters"]
    )

    def get_arg(name: str) -> str:
        i = params.index(name)
        return params[i + 1]

    credential = dbutils.secrets.get(
        scope=get_arg("--secret-scope"),
        key=get_arg("--secret-key"),
    )

    database = (
        CosmosClient(
            get_arg("--endpoint"),
            credential=credential,
        )
        .get_database_client("canopy-db")
    )

    ranking_container = database.get_container_client(
        RANKING_CONTAINER
    )

    users_container = database.get_container_client("users")

    # ----------------------------------------------------------
    # Reward Ledger sandbox
    # ----------------------------------------------------------
    ledger_df = (
        spark.table(SANDBOX_LEDGER_TABLE)
        .where(
            (F.col("campaign_id") == CAMPAIGN)
            & (F.col("week_label") == WEEK)
        )
    )

    assert ledger_df.count() == 3

    # ----------------------------------------------------------
    # Membership
    # ----------------------------------------------------------
    membership_df = (
        spark.read.format("delta")
        .load(MEMBERSHIP_PATH)
        .where(F.col("campaign_id") == CAMPAIGN)
    )

    # ----------------------------------------------------------
    # Existing Ranking transform
    # ----------------------------------------------------------
    policy = yaml.safe_load(
        (module_dir / "ranking_policy.yaml")
        .read_text(encoding="utf-8")
    )

    personal_result, department_result = build_ranking(
        ledger_df,
        membership_df,
        policy,
    )

    personal_rows = personal_result.orderBy("rank").collect()
    department_rows = department_result.orderBy("rank").collect()

    assert len(personal_rows) == 2

    expected_u01 = f"{CAMPAIGN}_u01"
    expected_u02 = f"{CAMPAIGN}_u02"

    assert personal_rows[0]["user_id"] == expected_u01
    assert float(personal_rows[0]["score"]) == 100.0
    assert int(personal_rows[0]["rank"]) == 1

    assert personal_rows[1]["user_id"] == expected_u02
    assert float(personal_rows[1]["score"]) == 80.0
    assert int(personal_rows[1]["rank"]) == 2

    def nickname(user_id: str) -> str:
        try:
            user = users_container.read_item(
                item=user_id,
                partition_key=user_id,
            )
            return user.get("nickname") or user_id
        except CosmosResourceNotFoundError:
            return user_id

    personal_entries = [
        {
            "user_id": row["user_id"],
            "nickname": nickname(row["user_id"]),
            "score_points": float(row["score"]),
            "rank": int(row["rank"]),
        }
        for row in personal_rows
    ]

    # Dedicated test campaign partition.
    # Existing campaign_canopy_01 documents cannot be overwritten.
    document = {
        "id": WEEK,
        "campaign_id": CAMPAIGN,
        "week": WEEK,
        "schema_version": "ranking-points-v1",
        "score_unit": "points",
        "personal_ranking": personal_entries,
        "department_ranking": [],
        "policy_version": personal_rows[0]["policy_version"],
        "generated_at": personal_rows[0]["generated_at"].isoformat(),
    }

    ranking_container.upsert_item(document)

    # Cosmos partition key is /campaign_id
    saved = ranking_container.read_item(
        item=WEEK,
        partition_key=CAMPAIGN,
    )

    assert saved["campaign_id"] == CAMPAIGN
    assert saved["week"] == WEEK
    assert saved["schema_version"] == "ranking-points-v1"
    assert saved["score_unit"] == "points"

    saved_personal = saved["personal_ranking"]

    assert len(saved_personal) == 2
    assert saved_personal[0]["score_points"] == 100.0
    assert saved_personal[0]["rank"] == 1
    assert saved_personal[1]["score_points"] == 80.0
    assert saved_personal[1]["rank"] == 2

    print(
        json.dumps(
            {
                "status":
                    "RANKING_EXISTING_COSMOS_VALIDATION_PASSED",
                "container": RANKING_CONTAINER,
                "campaign_id": CAMPAIGN,
                "week": WEEK,
                "schema_version": saved["schema_version"],
                "score_unit": saved["score_unit"],
                "personal_ranking": saved_personal,
                "department_ranking_row_count":
                    len(department_rows),
                "legacy_ranking_overwritten": False,
                "canonical_ranking_gold_written": False,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()