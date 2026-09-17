from datetime import datetime, timedelta, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql import Window

RANKING_VERSION = "build-ranking-v1"

PERSONAL_SCHEMA = (
    "campaign_id string, week string, user_id string, score double, rank long, "
    "generated_at timestamp, policy_version string, generation_version string"
)
DEPARTMENT_SCHEMA = (
    "campaign_id string, week string, department_id string, score double, rank long, "
    "generated_at timestamp, policy_version string, generation_version string"
)

GOLD_PERSONAL_RANKING_PATH = "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/ranking_personal/"
GOLD_DEPARTMENT_RANKING_PATH = "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/ranking_department/"


def _week_label_to_end_date(week_label):
    if week_label is None:
        return None
    year, week = week_label.split("-W")
    monday = datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()
    return (monday + timedelta(days=6)).isoformat()


_week_label_to_end_date_udf = F.udf(_week_label_to_end_date, T.StringType())


def _rank_column(tie_method):
    if tie_method is None:
        raise ValueError("ranking_policy.tie_handling.method not configured")
    if tie_method == "dense_rank":
        return F.dense_rank()
    if tie_method == "standard_competition_rank":
        return F.rank()
    raise ValueError(f"unsupported tie_handling.method: {tie_method}")


def build_ranking(paid_rewards_df, membership_df, policy):
    """Pure function: takes already-filtered paid rewards + membership DataFrames
    and a loaded policy dict, returns (personal_result_df, department_result_df).
    No table reads, no writes - fully testable in isolation.
    """
    tie_method = policy["tie_handling"]["method"]
    dept_method = policy["department_scoring"]["method"]
    minimum_participants = policy["department_scoring"].get("minimum_participants")
    policy_version = policy["policy_version"]
    generated_at = datetime.now(timezone.utc)

    deduped_rewards = paid_rewards_df.dropDuplicates(["reward_id"])

    personal_scores = deduped_rewards.groupBy("campaign_id", "week", "user_id").agg(
        F.sum("points").alias("score"),
    )

    w = Window.partitionBy("campaign_id", "week").orderBy(F.col("score").desc())
    personal_ranked = personal_scores.withColumn("rank", _rank_column(tie_method).over(w))

    personal_result = (
        personal_ranked
        .withColumn("generated_at", F.lit(generated_at))
        .withColumn("policy_version", F.lit(policy_version))
        .withColumn("generation_version", F.lit(RANKING_VERSION))
        .select("campaign_id", "week", "user_id", "score", "rank", "generated_at", "policy_version", "generation_version")
    )

    week_end_dates = personal_ranked.select("campaign_id", "week").distinct()
    week_end_dates = week_end_dates.withColumn("week_end_date", _week_label_to_end_date_udf(F.col("week")))

    with_membership = personal_ranked.join(membership_df, ["campaign_id", "user_id"], "left")
    with_membership = with_membership.join(week_end_dates, ["campaign_id", "week"], "left")
    with_membership = with_membership.filter(F.to_date(F.col("joined_at")) <= F.to_date(F.col("week_end_date")))
    with_membership = with_membership.filter(
        F.col("left_at").isNull() | (F.to_date(F.col("left_at")) > F.to_date(F.col("week_end_date")))
    )

    no_dept_count = with_membership.filter(F.col("department_id").isNull()).count()
    if no_dept_count > 0:
        print(f"[build_ranking] {no_dept_count}명이 department_id 없음 - 부서 랭킹에서 제외, 개인 랭킹에는 포함됨")

    with_dept = with_membership.filter(F.col("department_id").isNotNull())

    dept_grouped = with_dept.groupBy("campaign_id", "week", "department_id").agg(
        F.sum("score").alias("sum_score"),
        F.count("user_id").alias("member_count"),
    )

    if minimum_participants is not None:
        excluded_small = dept_grouped.filter(F.col("member_count") < minimum_participants).count()
        if excluded_small > 0:
            print(f"[build_ranking] 부서 {excluded_small}개가 최소인원({minimum_participants}명) 미달로 부서 랭킹에서 제외")
        dept_grouped = dept_grouped.filter(F.col("member_count") >= minimum_participants)

    if dept_method == "sum_of_member_points":
        dept_scored = dept_grouped.withColumn("score", F.col("sum_score"))
    elif dept_method == "average_per_member":
        dept_scored = dept_grouped.withColumn("score", F.col("sum_score") / F.col("member_count"))
    else:
        raise ValueError(f"unsupported department_scoring.method: {dept_method}")

    dept_w = Window.partitionBy("campaign_id", "week").orderBy(F.col("score").desc())
    dept_ranked = dept_scored.withColumn("rank", _rank_column(tie_method).over(dept_w))

    department_result = (
        dept_ranked
        .withColumn("generated_at", F.lit(generated_at))
        .withColumn("policy_version", F.lit(policy_version))
        .withColumn("generation_version", F.lit(RANKING_VERSION))
        .select("campaign_id", "week", "department_id", "score", "rank", "generated_at", "policy_version", "generation_version")
    )

    return personal_result, department_result


def _existing_snapshot_is_newer(spark, path, campaign_id, week, new_generated_at):
    try:
        existing = spark.read.format("delta").load(path).filter(
            (F.col("campaign_id") == campaign_id) & (F.col("week") == week)
        )
        row = existing.agg(F.max("generated_at").alias("latest")).first()
        if row is None or row["latest"] is None:
            return False
        return row["latest"] > new_generated_at
    except Exception:
        return False


def write_snapshot(spark, df, path, campaign_id, week):
    generated_at_row = df.filter(
        (F.col("campaign_id") == campaign_id) & (F.col("week") == week)
    ).agg(F.max("generated_at").alias("g")).first()
    new_generated_at = generated_at_row["g"] if generated_at_row else None

    if new_generated_at is not None and _existing_snapshot_is_newer(spark, path, campaign_id, week, new_generated_at):
        print(f"[write_snapshot] 기존 Snapshot이 이번 실행보다 최신 -> 덮어쓰지 않음 (campaign_id={campaign_id}, week={week})")
        return

    (
        df.write.format("delta")
        .mode("overwrite")
        .option("partitionOverwriteMode", "dynamic")
        .option("mergeSchema", "true")
        .partitionBy("campaign_id", "week")
        .save(path)
    )


def run(campaign_id, week, policy):
    spark = SparkSession.builder.getOrCreate()

    paid_rewards_df = (
        spark.read.table("reward_ledger_history")
        .filter(
            (F.col("campaign_id") == campaign_id)
            & (F.col("week_label") == week)
            & (F.col("status").isin(["paid", "adjusted"]))
        )
    )
    membership_df = spark.read.table("campaign_membership_raw").filter(F.col("campaign_id") == campaign_id)

    personal_result, department_result = build_ranking(paid_rewards_df, membership_df, policy)

    write_snapshot(spark, personal_result, GOLD_PERSONAL_RANKING_PATH, campaign_id, week)
    write_snapshot(spark, department_result, GOLD_DEPARTMENT_RANKING_PATH, campaign_id, week)

    print(f"[done] campaign_id={campaign_id} week={week} ranking snapshot complete")


if __name__ == "__main__":
    import sys

    import yaml

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_arg = sys.argv[2] if len(sys.argv) > 2 else None
    policy_path_arg = sys.argv[3] if len(sys.argv) > 3 else None

    if not (campaign_id_arg and week_arg and policy_path_arg):
        raise ValueError("campaign_id, week, policy_path parameters required")

    with open(policy_path_arg, "r", encoding="utf-8") as f:
        policy_arg = yaml.safe_load(f)

    run(campaign_id_arg, week_arg, policy_arg)
