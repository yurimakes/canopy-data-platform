import os
from datetime import datetime, timedelta, timezone

from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
from azure.identity import DefaultAzureCredential
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

COSMOS_DATABASE = os.environ.get("CANOPY_COSMOS_DATABASE", "canopy-db")
COSMOS_RANKING_SNAPSHOT_CONTAINER = os.environ.get("CANOPY_COSMOS_RANKING_SNAPSHOT_CONTAINER", "ranking-snapshots")
COSMOS_USERS_CONTAINER = os.environ.get("CANOPY_COSMOS_USERS_CONTAINER", "users")

GOLD_PERSONAL_RANKING_PATH = "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/ranking_personal/"
GOLD_DEPARTMENT_RANKING_PATH = "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/ranking_department/"

COSMOS_ENDPOINT = os.environ.get("CANOPY_COSMOS_ENDPOINT")

AGGREGATION_VERSION = "build-ranking-v1"


def _week_label_to_bounds(week_label):
    year, week = week_label.split("-W")
    monday = datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()


def _get_container(name):
    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    db = client.get_database_client(COSMOS_DATABASE)
    return db.get_container_client(name)


def _lookup_nickname(users_container, user_id):
    try:
        item = users_container.read_item(item=user_id, partition_key=user_id)
        return item.get("nickname") or user_id
    except cosmos_exceptions.CosmosResourceNotFoundError:
        return user_id


def publish_personal(spark, campaign_id, week):
    week_start, week_end = _week_label_to_bounds(week)

    df = (
        spark.read.format("delta").load(GOLD_PERSONAL_RANKING_PATH)
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week))
        .orderBy("rank")
    )
    rows = df.collect()
    if not rows:
        return 0

    users_container = _get_container(COSMOS_USERS_CONTAINER)
    entries = [
        {
            "rank": row["rank"],
            # user_id: is_me 계산에만 쓰는 내부 필드. API 응답에는 절대 노출 안 됨(engagement_read_service가 걸러냄).
            "user_id": row["user_id"],
            # public_subject_id: 실제로 응답에 노출되는 값. 별도 익명화 방식이 확정되기 전까지는
            # user_id와 동일값을 씀 - 진짜 익명 식별자가 필요하면 팀 확인 후 교체 필요.
            "public_subject_id": row["user_id"],
            "display_name": _lookup_nickname(users_container, row["user_id"]),
            "score": row["score"],
        }
        for row in rows
    ]

    doc = {
        "id": f"ranking:individual:{campaign_id}:{week_start}",
        "pk": f"{campaign_id}:{week_start}",
        "campaign_id": campaign_id,
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
    ranking_container = _get_container(COSMOS_RANKING_SNAPSHOT_CONTAINER)
    ranking_container.upsert_item(doc)
    return len(entries)


def publish_department(spark, campaign_id, week):
    week_start, week_end = _week_label_to_bounds(week)

    df = (
        spark.read.format("delta").load(GOLD_DEPARTMENT_RANKING_PATH)
        .filter((F.col("campaign_id") == campaign_id) & (F.col("week") == week))
        .orderBy("rank")
    )
    rows = df.collect()
    if not rows:
        return 0

    # TODO: 부서 표시명 소스가 아직 없음. 확인 전까지 department_id를 그대로 씀.
    entries = [
        {
            "rank": row["rank"],
            "public_subject_id": row["department_id"],
            "display_name": row["department_id"],
            "score": row["score"],
            # member_user_ids: is_me 계산에만 쓰는 내부 필드. 응답에는 노출 안 됨.
            "member_user_ids": list(row["member_user_ids"]),
        }
        for row in rows
    ]

    doc = {
        "id": f"ranking:department:{campaign_id}:{week_start}",
        "pk": f"{campaign_id}:{week_start}",
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "scope": "department",
        "snapshot_status": "finalized",
        "generated_at": rows[0]["generated_at"].isoformat(),
        "policy_version": rows[0]["policy_version"],
        "aggregation_version": AGGREGATION_VERSION,
        "score_unit": "points",
        "entries": entries,
    }
    ranking_container = _get_container(COSMOS_RANKING_SNAPSHOT_CONTAINER)
    ranking_container.upsert_item(doc)
    return len(entries)


def run(campaign_id, week):
    spark = SparkSession.builder.getOrCreate()

    personal_count = publish_personal(spark, campaign_id, week)
    department_count = publish_department(spark, campaign_id, week)

    print(f"[done] campaign_id={campaign_id} week={week} published individual_entries={personal_count} department_entries={department_count}")


if __name__ == "__main__":
    import sys

    campaign_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    week_arg = sys.argv[2] if len(sys.argv) > 2 else None

    if not (campaign_id_arg and week_arg):
        raise ValueError("campaign_id and week parameters required")

    run(campaign_id_arg, week_arg)
