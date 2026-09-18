"""Validate Personal Ranking -> actual dev Cosmos ranking-snapshots.

Scope:
- Use existing sandbox Reward Ledger.
- Use existing campaign membership.
- Run existing build_ranking().
- Publish ONLY the dedicated test campaign personal ranking snapshot.
- Do not write canonical Ranking Gold.
- Do not publish department ranking.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


CAMPAIGN = "pipeline_test_weekly_20260918"
WEEK = "2026-W38"

SANDBOX_LEDGER_TABLE = "dbw_canopy_dev.sandbox.reward_ledger_history"

MEMBERSHIP_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/"
    "curated/campaign_membership_raw/"
)

RANKING_CONTAINER = "ranking-snapshots"
USERS_CONTAINER = "users"

AGGREGATION_VERSION = "build-ranking-v1"


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

    raise RuntimeError(
        "Repository root not found. "
        "Run from the canopy-data-platform Databricks Git Folder."
    )


def week_bounds(week_label: str) -> tuple[str, str]:
    year, week = week_label.split("-W")
    monday = datetime.strptime(
        f"{year}-W{week}-1",
        "%G-W%V-%u",
    ).date()

    sunday = monday + timedelta(days=6)

    return monday.isoformat(), sunday.isoformat()


def main() -> None:
    if not CAMPAIGN.startswith("pipeline_test_weekly_"):
        raise ValueError("Only weekly test campaign is allowed.")

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

    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    from build_ranking import build_ranking

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    # ----------------------------------------------------------
    # Existing team Cosmos configuration
    # ----------------------------------------------------------
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
        index = params.index(name)
        return params[index + 1]

    endpoint = get_arg("--endpoint")
    secret_scope = get_arg("--secret-scope")
    secret_key = get_arg("--secret-key")

    credential = dbutils.secrets.get(
        scope=secret_scope,
        key=secret_key,
    )

    cosmos = CosmosClient(
        endpoint,
        credential=credential,
    )

    database = cosmos.get_database_client("canopy-db")

    ranking_container = database.get_container_client(
        RANKING_CONTAINER
    )

    users_container = database.get_container_client(
        USERS_CONTAINER
    )

    # ----------------------------------------------------------
    # Reward Ledger sandbox input
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
    # Membership input
    # ----------------------------------------------------------
    membership_df = (
        spark.read.format("delta")
        .load(MEMBERSHIP_PATH)
        .where(F.col("campaign_id") == CAMPAIGN)
    )

    # ----------------------------------------------------------
    # Existing ranking policy / transform
    # ----------------------------------------------------------
    policy = yaml.safe_load(
        (module_dir / "ranking_policy.yaml")
        .read_text(encoding="utf-8")
    )

    personal_result, _ = build_ranking(
        ledger_df,
        membership_df,
        policy,
    )

    rows = personal_result.orderBy("rank").collect()

    assert len(rows) == 2, rows

    expected_u01 = f"{CAMPAIGN}_u01"
    expected_u02 = f"{CAMPAIGN}_u02"

    assert rows[0]["user_id"] == expected_u01
    assert float(rows[0]["score"]) == 100.0
    assert int(rows[0]["rank"]) == 1

    assert rows[1]["user_id"] == expected_u02
    assert float(rows[1]["score"]) == 80.0
    assert int(rows[1]["rank"]) == 2

    # ----------------------------------------------------------
    # Nickname lookup
    # ----------------------------------------------------------
    def display_name(user_id: str) -> str:
        try:
            doc = users_container.read_item(
                item=user_id,
                partition_key=user_id,
            )
            return doc.get("nickname") or user_id

        except CosmosResourceNotFoundError:
            return user_id

    entries = [
        {
            "rank": int(row["rank"]),
            "user_id": row["user_id"],
            "public_subject_id": row["user_id"],
            "display_name": display_name(row["user_id"]),
            "score": float(row["score"]),
        }
        for row in rows
    ]

    week_start, week_end = week_bounds(WEEK)

    document_id = (
        f"ranking:individual:{CAMPAIGN}:{week_start}"
    )

    partition_key = f"{CAMPAIGN}:{week_start}"

    doc = {
        "id": document_id,
        "pk": partition_key,
        "campaign_id": CAMPAIGN,
        "week_start": week_start,
        "week_end": week_end,
        "scope": "individual",
        "snapshot_status": "finalized",
        "generated_at": rows[0]["generated_at"].isoformat(),
        "policy_version": rows[0]["policy_version"],
        "aggregation_version": AGGREGATION_VERSION,
        "score_unit": "points",
        "entries": entries,
    }

    # Existing container only.
    # Container creation is intentionally excluded.
    ranking_container.upsert_item(doc)

    # ----------------------------------------------------------
    # Read-back verification
    # ----------------------------------------------------------
    saved = ranking_container.read_item(
        item=document_id,
        partition_key=partition_key,
    )

    saved_entries = saved.get("entries", [])

    assert len(saved_entries) == 2, saved_entries

    assert saved_entries[0]["rank"] == 1
    assert float(saved_entries[0]["score"]) == 100.0

    assert saved_entries[1]["rank"] == 2
    assert float(saved_entries[1]["score"]) == 80.0

    print(
        json.dumps(
            {
                "status":
                    "RANKING_COSMOS_PUBLISH_VALIDATION_PASSED",
                "campaign_id": CAMPAIGN,
                "week": WEEK,
                "scope": "individual",
                "entry_count": len(saved_entries),
                "entries": [
                    {
                        "public_subject_id":
                            entry["public_subject_id"],
                        "display_name":
                            entry["display_name"],
                        "score": float(entry["score"]),
                        "rank": int(entry["rank"]),
                    }
                    for entry in saved_entries
                ],
                "ranking_cosmos_published": True,
                "canonical_ranking_gold_written": False,
                "department_ranking_published": False,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()