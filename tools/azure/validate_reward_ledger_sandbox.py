"""Runtime validation for Reward Ledger history materialization in Databricks sandbox.

This script writes only to dbw_canopy_dev.sandbox.reward_ledger_history and uses
synthetic in-memory Reward Ledger rows. It does not call Cosmos and does not write
canonical Gold.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pyspark.sql import SparkSession, functions as F


SANDBOX_TARGET = "table:dbw_canopy_dev.sandbox.reward_ledger_history"
TEST_CAMPAIGN = "pipeline_test_reward_ledger_20260918"
TEST_WEEK = "2026-W38"


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]


def _reward_module():
    root = _repo_root()
    module_dir = root / "cloud" / "azure" / "pipelines" / "databricks"
    sys.path.insert(0, str(module_dir))
    import reward_ledger  # noqa: PLC0415

    return reward_ledger


class FakeRewardContainer:
    def __init__(self, rows):
        self.rows = rows

    def query_items(self, *, query, parameters, enable_cross_partition_query):
        assert "c.campaign_id = @campaign_id" in query
        assert "c.week_label = @week_label" in query
        assert enable_cross_partition_query is True
        params = {p["name"]: p["value"] for p in parameters}
        assert params["@campaign_id"] == TEST_CAMPAIGN
        assert params["@week_label"] == TEST_WEEK
        return list(self.rows)


def _rows():
    return [
        {
            "id": "reward-test-u01",
            "reward_id": "reward-test-u01",
            "user_id": "pipeline_test_reward_u01",
            "campaign_id": TEST_CAMPAIGN,
            "week": "2026-09-14",
            "week_label": TEST_WEEK,
            "label": "synthetic paid reward",
            "points": 120.0,
            "status": "paid",
            "occurred_at": "2026-09-18T00:00:00+00:00",
            "policy_version": "reward-policy-v1",
        },
        {
            "id": "reward-test-u02",
            "reward_id": "reward-test-u02",
            "user_id": "pipeline_test_reward_u02",
            "campaign_id": TEST_CAMPAIGN,
            "week": "2026-09-14",
            "week_label": TEST_WEEK,
            "label": "synthetic paid reward",
            "points": 80.0,
            "status": "paid",
            "occurred_at": "2026-09-18T00:00:01+00:00",
            "policy_version": "reward-policy-v1",
        },
        {
            "id": "adjustment-reward-test-u01",
            "reward_id": "adjustment-reward-test-u01",
            "adjusts_reward_id": "reward-test-u01",
            "user_id": "pipeline_test_reward_u01",
            "campaign_id": TEST_CAMPAIGN,
            "week": "2026-09-14",
            "week_label": TEST_WEEK,
            "label": "synthetic adjustment",
            "points": -20.0,
            "status": "adjusted",
            "occurred_at": "2026-09-18T00:00:02+00:00",
            "policy_version": "reward-policy-v1",
        },
    ]


def _read_test_partition(spark):
    return (
        spark.table("dbw_canopy_dev.sandbox.reward_ledger_history")
        .where(
            (F.col("campaign_id") == TEST_CAMPAIGN)
            & (F.col("week_label") == TEST_WEEK)
        )
    )


def verify_partition(spark):
    df = _read_test_partition(spark)
    rows = [r.asDict(recursive=True) for r in df.orderBy("reward_id").collect()]
    assert len(rows) == 3, rows

    status_counts = {
        r["status"]: r["count"]
        for r in df.groupBy("status").count().collect()
    }
    assert status_counts == {"paid": 2, "adjusted": 1}, status_counts

    reward_ids = [r["reward_id"] for r in rows]
    assert len(reward_ids) == len(set(reward_ids)), reward_ids

    total_points = df.agg(F.sum("points").alias("points")).first()["points"]
    assert total_points == 180.0, total_points

    return {
        "row_count": len(rows),
        "status_counts": status_counts,
        "total_points": total_points,
    }


def main():
    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    reward_ledger = _reward_module()
    container = FakeRewardContainer(_rows())

    first_count = reward_ledger.sync_ledger_history_from_cosmos(
        spark,
        container,
        TEST_CAMPAIGN,
        TEST_WEEK,
        target=SANDBOX_TARGET,
    )
    first = verify_partition(spark)

    second_count = reward_ledger.sync_ledger_history_from_cosmos(
        spark,
        container,
        TEST_CAMPAIGN,
        TEST_WEEK,
        target=SANDBOX_TARGET,
    )
    second = verify_partition(spark)

    assert first_count == 3
    assert second_count == 3
    assert first == second

    print(
        json.dumps(
            {
                "status": "REWARD_LEDGER_SANDBOX_VALIDATION_PASSED",
                "target": SANDBOX_TARGET,
                "campaign_id": TEST_CAMPAIGN,
                "week": TEST_WEEK,
                "first": first,
                "second": second,
                "cosmos_called": False,
                "canonical_gold_written": False,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
