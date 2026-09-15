from __future__ import annotations

import sys

from baseline_runtime import load_cosmos_identity, load_cosmos_targets, load_gold_paths
from cosmos_baseline_writer import (
    global_latest_documents,
    personal_latest_documents,
    verify_latest_documents,
    write_latest_documents,
)


def run(campaign_id: str, evaluation_week: str) -> None:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = SparkSession.builder.getOrCreate()
    paths = load_gold_paths()
    identity = load_cosmos_identity()
    targets = load_cosmos_targets()

    personal = (
        spark.read.format("delta")
        .load(paths.personal_history)
        .filter(
            (F.col("campaign_id") == campaign_id)
            & (F.col("week") == evaluation_week)
        )
    )
    global_df = (
        spark.read.format("delta")
        .load(paths.global_history)
        .filter(
            (F.col("campaign_id") == campaign_id)
            & (F.col("week") == evaluation_week)
        )
    )

    global_count = global_df.count()
    if global_count != 1:
        raise RuntimeError(
            f"Expected exactly one Global baseline row for {campaign_id}/{evaluation_week}; "
            f"found {global_count}."
        )

    personal_docs = personal_latest_documents(personal)
    global_docs = global_latest_documents(global_df)

    if personal_docs.limit(1).count():
        write_latest_documents(
            personal_docs,
            identity,
            container=targets.personal_container,
        )
        verify_latest_documents(
            personal_docs,
            identity,
            container=targets.personal_container,
        )

    write_latest_documents(
        global_docs,
        identity,
        container=targets.global_container,
    )
    verify_latest_documents(
        global_docs,
        identity,
        container=targets.global_container,
    )

    print(
        f"[done] campaign_id={campaign_id} evaluation_week={evaluation_week} "
        "ADLS Gold -> Cosmos latest Baseline publish verified"
    )


if __name__ == "__main__":
    try:
        campaign_id_arg = dbutils.widgets.get("campaign_id")  # noqa: F821
        evaluation_week_arg = dbutils.widgets.get("evaluation_week")  # noqa: F821
    except NameError:
        campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
        evaluation_week_arg = sys.argv[2] if len(sys.argv) > 2 else None

    if not campaign_id_arg:
        raise ValueError("campaign_id parameter required")
    if not evaluation_week_arg:
        raise ValueError("evaluation_week parameter required")

    run(campaign_id_arg, evaluation_week_arg)
