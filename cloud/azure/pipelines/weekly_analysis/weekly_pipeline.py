"""주간 분석 파이프라인 초기 뼈대.

최종 Trip 읽기 → 주간 집계 → weekly_gold 저장까지 실제 코드 연결.
이후 블록은 컬럼과 연결 관계만 정의한 0행 결과 반환. 담당 계산 코드 입력 필요.
현재 입력은 개발용 Final Trip 경로이며 Mock 결과 포함 가능. 운영 출퇴근 입력과 구분.
각 블록의 empty_result(...) 부분을 담당자의 계산 코드와 결과 DataFrame 반환으로 교체.
입력 테이블 조회 → 계산 → 결과 DataFrame 반환 순서로 작성.
함수 내부에서 직접 저장, Cosmos 호출, 다른 Job 실행 제외.
테이블 생성과 갱신은 파이프라인에서 처리. Cosmos 반영은 바깥 Job의 후속 작업.
미구현 블록도 실제 출력 컬럼을 가진 0행 결과 반환. 컬럼 초안은 블록 설명에 표시.
가입 정보, 미션 응답 이력, 실제 보상 이력 등 외부 입력은 담당 코드 연결 시 추가.
실행 시작: 바깥 Job의 run_weekly_pipeline. 데이터 입력 시작: final_trip_gold_input().
"""
import sys
import os
import pandas as pd
from pyspark import pipelines as dp
from pyspark.sql.functions import pandas_udf
from pyspark.sql import SparkSession, Window, functions as F, types as T

# 깃 폴더 경로 지정
git_module_path = "/Workspace/canopy-data-platform-git/cloud/azure/pipelines/databricks"
if git_module_path not in sys.path:
    sys.path.append(git_module_path)

# 파이프라인 실행에 필요한 함수 및 모듈 임포트
from baseline_eligibility import load_eligibility_policy, evaluate_personal_eligibility, observation_context, week_evaluation_time
from build_personal_baseline import load_policy as load_baseline_policy
from helpers.spark_baseline import (
    build_personal_baseline as build_personal_baseline_df,
    select_personal_ready_users,
    build_global_eligibility,
    build_global_baseline as build_global_baseline_df,
)

policy = load_eligibility_policy()
spark = SparkSession.builder.getOrCreate()


# 기존 build_personal_baseline.py가 쓰는 정책 파일 그대로 사용
BASELINE_POLICY = load_baseline_policy(
    os.path.join(git_module_path, "baseline_policy.yaml")
)
BASELINE_POLICY_VERSION = BASELINE_POLICY["policy_version"]

# 기존 Personal 코드에서 출퇴근 범위가 확인된 경우에만 Personal Baseline 계산
COMMUTE_SCOPE_VERIFIED = (
    os.environ.get("CANOPY_BASELINE_WEEKLY_COMMUTE_VERIFIED") == "true"
)

# 기존 계약: shared/schemas/baseline/weekly_user_gold.schema.json
WEEKLY_SCHEMA = """
    `user_id` STRING,
    `campaign_id` STRING,
    `week` STRING,
    `trip_count` BIGINT,
    `total_distance_m` DOUBLE,
    `total_kg_co2e` DOUBLE,
    `carbon_policy_version` STRING,
    `factor_version` STRING,
    `walk_distance_m` DOUBLE,
    `bike_distance_m` DOUBLE,
    `car_distance_m` DOUBLE,
    `bus_distance_m` DOUBLE,
    `rail_distance_m` DOUBLE,
    `mode_trip_ratio_walk` DOUBLE,
    `mode_trip_ratio_bike` DOUBLE,
    `mode_trip_ratio_car` DOUBLE,
    `mode_trip_ratio_bus` DOUBLE,
    `mode_trip_ratio_rail` DOUBLE,
    `mode_distance_ratio_walk` DOUBLE,
    `mode_distance_ratio_bike` DOUBLE,
    `mode_distance_ratio_car` DOUBLE,
    `mode_distance_ratio_bus` DOUBLE,
    `mode_distance_ratio_rail` DOUBLE,
    `mode_carbon_ratio_walk` DOUBLE,
    `mode_carbon_ratio_bike` DOUBLE,
    `mode_carbon_ratio_car` DOUBLE,
    `mode_carbon_ratio_bus` DOUBLE,
    `mode_carbon_ratio_rail` DOUBLE,
    `valid_primary_trip_count` BIGINT,
    `invalid_primary_trip_count` BIGINT,
    `ambiguous_primary_trip_count` BIGINT,
    `invalid_segment_primary_trip_count` BIGINT,
    `car_primary_trip_count` BIGINT,
    `transit_primary_trip_count` BIGINT,
    `low_carbon_trip_count` BIGINT,
    `short_car_trip_count` BIGINT,
    `car_primary_ratio` DOUBLE,
    `short_car_share` DOUBLE
"""

# 기존 계약: shared/schemas/baseline/personal_baseline.schema.json
PERSONAL_SCHEMA = """
    `user_id` STRING,
    `campaign_id` STRING,
    `week` STRING,
    `cumulative_g_co2e` DOUBLE,
    `cumulative_distance_km` DOUBLE,
    `baseline_g_co2e_per_km` DOUBLE,
    `method` STRING,
    `policy_version` STRING,
    `status` STRING,
    `value` DOUBLE,
    `eligibility_policy_version` STRING,
    `observation_days` BIGINT,
    `confirmed_trip_count` BIGINT,
    `observation_source` STRING,
    `eligibility_reason` STRING,
    `primary_baseline` STRING
"""

# 기존 계약: shared/schemas/baseline/global_baseline.schema.json
GLOBAL_SCHEMA = """
    `campaign_id` STRING,
    `week` STRING,
    `valid_participant_count` BIGINT,
    `baseline_g_co2e_per_km` DOUBLE,
    `method` STRING,
    `policy_version` STRING,
    `status` STRING,
    `value` DOUBLE,
    `eligible_participant_count` BIGINT,
    `eligibility_policy_version` STRING
"""

# 기존 계약: shared/schemas/mission/mission_bundle.schema.json
MISSION_BUNDLE_SCHEMA = """
    `id` STRING,
    `pk` STRING,
    `type` STRING,
    `bundle_id` STRING,
    `user_id` STRING,
    `campaign_id` STRING,
    `week_start` STRING,
    `week_end` STRING,
    `policy_version` STRING,
    `policy_hash` STRING,
    `profile_source_week` STRING,
    `profile_version` STRING,
    `profile_hash` STRING,
    `profile_status_at_issue` STRING,
    `common_target_count` BIGINT,
    `difficulty_reason` STRING,
    `created_at` STRING,
    `missions` ARRAY<STRUCT<`assignment_id`: STRING, `category_id`: STRING, `category_label`: STRING, `mission_template_id`: STRING, `mission_family`: STRING, `mission_name`: STRING, `mission_description`: STRING, `progress_unit`: STRING, `difficulty_band`: STRING, `common_target_count`: BIGINT, `target_count`: BIGINT, `affinity_comparable`: BOOLEAN, `difficulty_comparable`: BOOLEAN, `preference_comparable`: BOOLEAN, `completion_rule`: STRUCT<`metric`: STRING, `accepted_primary_modes`: ARRAY<STRING>, `min_trip_distance_km`: DOUBLE, `max_trip_distance_km`: DOUBLE, `date_field`: STRING, `target_count`: BIGINT, `dedupe_key`: STRING, `time_window`: STRING, `source`: STRING>, `progress_count`: BIGINT, `achievement_rate`: DOUBLE, `completed`: BOOLEAN, `status`: STRING>>
"""

# 기존 Gold 출력: build_mission_profile.py의 run() schema와 _gold_profile()
PROFILE_SCHEMA = """
    `type` STRING,
    `profile_version` STRING,
    `profile_status` STRING,
    `user_id` STRING,
    `campaign_id` STRING,
    `source_week_start` STRING,
    `source_week_end` STRING,
    `effective_week_start` STRING,
    `valid_trip_count` INT,
    `invalid_trip_count` INT,
    `invalid_trip_reasons` MAP<STRING, INT>,
    `car_primary_trip_count` INT,
    `car_ratio` DOUBLE,
    `short_car_trip_count` INT,
    `short_car_share` DOUBLE,
    `transit_primary_trip_count` INT,
    `low_carbon_trip_count` INT,
    `carbon_change_rate` DOUBLE,
    `mission_history_source` STRING,
    `preference_positive_evidence_count` INT,
    `category_preferences_json` STRING,
    `difficulty_state_json` STRING,
    `family_capability_json` STRING,
    `profile_hash` STRING
"""

# 기존 판정 함수 반환값에 사용자, 캠페인, 적용 주차 식별자 연결
# 원본: baseline_eligibility.py
PERSONAL_ELIGIBILITY_SCHEMA = """
    user_id STRING, campaign_id STRING, week STRING,
    status STRING, policy_version STRING, observation_days BIGINT,
    confirmed_trip_count BIGINT, reasons ARRAY<STRING>
"""
GLOBAL_ELIGIBILITY_SCHEMA = """
    campaign_id STRING, week STRING, status STRING,
    policy_version STRING, eligible_participant_count BIGINT
"""

# 통합 저장 형태 초안. 개인과 Global 원본 컬럼을 별도 구조로 보존
# 계산 및 소비 코드 연결 전 팀 확인 필요
BASELINE_GOLD_SCHEMA = f"""
    campaign_id STRING, user_id STRING, week STRING,
    personal STRUCT<{PERSONAL_SCHEMA}>, global STRUCT<{GLOBAL_SCHEMA}>
"""

# 이하 컬럼 초안. 저장 계약 미제출 단계이며 담당자 확인 전 계산과 발행 제외
# 행동 변화: 전후 관찰 기간, 탄소 단위, 판정 근거 확인 필요
BEHAVIOR_DRAFT_SCHEMA = """
    user_id STRING, campaign_id STRING, week STRING,
    before_week_start STRING, before_week_end STRING,
    after_week_start STRING, after_week_end STRING,
    before_avg_weekly_kg_co2e DOUBLE, after_avg_weekly_kg_co2e DOUBLE,
    change_kg_co2e DOUBLE, change_rate DOUBLE,
    status STRING, reason STRING, policy_version STRING
"""
# 랭킹: 실제 지급 및 조정 합계 입력 기준. 포인트 단위와 동점 처리 합의 필요
RANKING_DRAFT_SCHEMA = """
    campaign_id STRING, week STRING, ranking_type STRING,
    user_id STRING, department_id STRING,
    reward_points DOUBLE, rank BIGINT,
    policy_version STRING, generated_at TIMESTAMP
"""
# 캠페인 지표: 비율별 분모와 탄소 절감 기준 합의 필요
CAMPAIGN_KPI_DRAFT_SCHEMA = """
    campaign_id STRING, week STRING,
    enrolled_user_count BIGINT, active_user_count BIGINT,
    participation_rate DOUBLE, trip_count BIGINT,
    total_distance_m DOUBLE, total_kg_co2e DOUBLE,
    assigned_mission_count BIGINT, completed_mission_count BIGINT,
    mission_completion_rate DOUBLE, changed_user_count BIGINT,
    behavior_evaluable_user_count BIGINT, paid_reward_points DOUBLE,
    policy_version STRING, generated_at TIMESTAMP
"""

# 최종 묶음 형태 초안. 개별 Gold 테이블을 단순 union하지 않고 결과별 구조 유지
# Cosmos 전송 계약이나 운영 이력 저장 계약으로 확정한 형식 아님
WEEKLY_OUTPUTS_DRAFT_SCHEMA = f"""
    campaign_id STRING, user_id STRING, week STRING,
    weekly STRUCT<{WEEKLY_SCHEMA}>, baseline STRUCT<{BASELINE_GOLD_SCHEMA}>,
    profile STRUCT<{PROFILE_SCHEMA}>, missions STRUCT<{MISSION_BUNDLE_SCHEMA}>,
    ranking ARRAY<STRUCT<{RANKING_DRAFT_SCHEMA}>>,
    campaign_kpi STRUCT<{CAMPAIGN_KPI_DRAFT_SCHEMA}>
"""


def empty_result(schema, *parents):
    """실제 출력 컬럼을 가진 0행 결과. 앞 단계 의존관계 유지, 계산 결과 생성 없음."""
    if not parents:
        return spark.createDataFrame([], schema)
    frames = [spark.read.table(parent).limit(0).select(
        F.from_json(F.lit("{}"), schema).alias("result")
    ).select("result.*") for parent in parents]
    frame = frames[0]
    for parent in frames[1:]:
        frame = frame.unionByName(parent)
    return frame


# 기존 개발용 Final Trip 저장 경로. 운영 입력으로 전환 시 담당자와 경로 확인
FINAL_TRIP_PATH = "abfss://curated@stcanopydev5dt.dfs.core.windows.net/pipeline_test/trip_finalization/iphone_final_trips"
MODES = ["walk", "bike", "car", "bus", "rail"]
LOW_CARBON_MODES = ["walk", "bike", "bus", "rail"]
TRANSIT_MODES = ["bus", "rail"]
SHORT_CAR_MAX_DISTANCE_M = 2000.0

# 기존 Final Trip Delta 출력: finalize_trip_pipeline.py의 gold_frame()
FINAL_TRIP_SCHEMA = """
    trip_id STRING, user_id STRING, campaign_id STRING, status STRING,
    started_at STRING, ended_at STRING, updated_at STRING, is_mock BOOLEAN,
    processing_generation BIGINT, finalization_hash STRING,
    segments ARRAY<STRUCT<segment_id:STRING, model_prediction:STRING,
        distance_m:DOUBLE, carbon_kg:DOUBLE>>,
    carbon STRUCT<kg_co2e:DOUBLE, policy_version:STRING,
        factor_version:STRING, unit:STRING>,
    document_json STRING
"""


@dp.temporary_view(comment="최종 Trip Delta 조회. 최신 완료 Trip 입력")
def final_trip_gold_input():
    # 기존 개발용 Final Trip 저장 결과 입력. Cosmos 조회 제외
    # 동일 사용자와 Trip의 최신 버전 선택 후 완료 상태 필터
    # 전체 저장 이력을 주차별 집계. 이번 주는 진행 중 집계이며 마감 결과와 구분 필요
    trips = spark.read.format("delta").load(FINAL_TRIP_PATH)
    latest = Window.partitionBy("campaign_id", "user_id", "trip_id").orderBy(
        F.to_timestamp("updated_at").desc())
    return (trips.withColumn("_latest", F.row_number().over(latest))
            .filter(F.col("_latest") == 1).drop("_latest")
            .filter(F.col("status") == "ready"))


@dp.temporary_view(comment="한국시간 기준 사용자별 주간 거리와 탄소 집계")
def weekly_summary():
    # 원본: build_weekly_summary.py
    # 입력: final_trip_gold_input / 출력: shared/schemas/baseline/weekly_user_gold.schema.json
    # 거리 m, 탄소 kgCO2e. 저장된 탄소 합계 사용, 배출계수 재계산 제외
    return calculate_weekly(spark.read.table("final_trip_gold_input"))


@dp.materialized_view(schema=WEEKLY_SCHEMA, comment="개발용 주간 집계 결과. 사용자, 캠페인, 주차별 한 행")
def weekly_gold():
    # 계산 결과 저장. 실제 출력 컬럼 유지
    return spark.read.table("weekly_summary").select(*T.StructType.fromDDL(WEEKLY_SCHEMA).fieldNames())


@dp.temporary_view(comment="Baseline 계산 대상 판정 코드 입력 위치")
def baseline_eligibility():
    weekly_df = spark.read.table("dbw_canopy_dev.weekly_analysis_scaffold.weekly_gold")

    agg_df = weekly_df.groupBy("user_id", "campaign_id", "week").agg(
        F.sum("trip_count").alias("trip_count"),
        F.sum("total_distance_m").alias("total_distance"),
        F.sum("total_kg_co2e").alias("total_carbon")
    )

    @pandas_udf(PERSONAL_ELIGIBILITY_SCHEMA)
    def evaluate_personal_row(
        user_id: pd.Series,
        campaign_id: pd.Series,
        week: pd.Series,
        trip_count: pd.Series,
        total_distance: pd.Series,
        total_carbon: pd.Series
    ) -> pd.DataFrame:
        results = []
        for uid, cid, w, tc, td, tc_carb in zip(
            user_id, campaign_id, week, trip_count, total_distance, total_carbon
        ):
            try:
                evaluated_at = week_evaluation_time(w)
            except Exception:
                evaluated_at = None

            identities = {
                "users": [],
                "memberships": []
            }

            obs_days, source, err = observation_context(uid, cid, evaluated_at, identities)
            observation_days = int(obs_days) if obs_days is not None else 0

            result = evaluate_personal_eligibility(
                observation_days=observation_days,
                trip_count=tc or 0,
                total_distance=td or 0.0,
                total_carbon=tc_carb or 0.0,
                policy=policy
            )

            results.append({
                "user_id": uid,
                "campaign_id": cid,
                "week": w,
                "status": result.get("status"),
                "policy_version": result.get("policy_version"),
                "observation_days": observation_days,
                "confirmed_trip_count": int(result.get("confirmed_trip_count", tc or 0)),
                "reasons": result.get("reasons", [])
            })

        return pd.DataFrame(results)

    return agg_df.select(
        evaluate_personal_row(
            F.col("user_id"),
            F.col("campaign_id"),
            F.col("week"),
            F.col("trip_count"),
            F.col("total_distance"),
            F.col("total_carbon")
        ).alias("evaluated")
    ).select("evaluated.*")


@dp.temporary_view(comment="이전 완료 주 이력을 이용한 개인 Baseline 계산")
def personal_baseline():
    return build_personal_baseline_df(
        weekly=spark.read.table("weekly_gold"),
        eligibility=spark.read.table("baseline_eligibility"),
        baseline_policy_version=BASELINE_POLICY_VERSION,
        commute_scope_verified=COMMUTE_SCOPE_VERIFIED,
        eligibility_policy=policy,
    )


@dp.temporary_view(comment="Global Baseline 계산에 사용할 준비 완료 Personal 사용자 선택")
def personal_ready_users():
    return select_personal_ready_users(
        spark.read.table("personal_baseline"),
        eligibility_policy=policy,
    )


@dp.temporary_view(comment="Global Baseline 계산 가능 여부 판정")
def global_eligibility():
    return build_global_eligibility(
        personal=spark.read.table("personal_baseline"),
        ready=spark.read.table("personal_ready_users"),
        eligibility_policy=policy,
    )


@dp.temporary_view(comment="Global Baseline 계산 및 갱신")
def global_baseline():
    return build_global_baseline_df(
        ready=spark.read.table("personal_ready_users"),
        eligibility=spark.read.table("global_eligibility"),
        baseline_policy_version=BASELINE_POLICY_VERSION,
        eligibility_policy=policy,
    )


@dp.materialized_view(schema=BASELINE_GOLD_SCHEMA, comment="계산 미연결. 개인과 Global 통합 형태는 컬럼 초안")
def baseline_gold():
    # 개인 결과와 Global 결과의 저장 형식 지정. 서로 다른 컬럼의 단순 합치기 제외
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(BASELINE_GOLD_SCHEMA, "personal_baseline", "global_baseline")


@dp.temporary_view(comment="계산 미연결. 행동 변화 컬럼 초안, 담당자 확정 필요")
def behavior_change():
    # 담당 코드에서 필요한 주간 이력, Baseline, 미션 이력 연결 → 행동 변화 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(BEHAVIOR_DRAFT_SCHEMA, "weekly_gold", "baseline_gold")


@dp.temporary_view(comment="계산 미연결. 기존 미션 프로필 Gold 출력 컬럼")
def weekly_user_profile():
    # 주간 집계와 미션 응답 이력 연결 → 사용자 프로필 반환. 초기 연결선은 담당 코드 기준으로 조정
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(PROFILE_SCHEMA, "weekly_gold")


@dp.materialized_view(schema=MISSION_BUNDLE_SCHEMA, comment="계산 미연결. 기존 mission_bundle.v1 출력 컬럼")
def next_week_missions():
    # 사용자 프로필과 미션 정책 입력 → 다음 주 미션 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(MISSION_BUNDLE_SCHEMA, "weekly_user_profile")


@dp.materialized_view(schema=RANKING_DRAFT_SCHEMA, comment="계산 미연결. 랭킹 컬럼 초안, 담당자 확정 필요")
def ranking():
    # 실제 보상 지급 이력과 소속 정보 연결 → 사용자 및 부서별 랭킹 반환. 초기 연결선 조정 필요
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(RANKING_DRAFT_SCHEMA, "weekly_user_profile")


@dp.materialized_view(schema=CAMPAIGN_KPI_DRAFT_SCHEMA, comment="계산 미연결. 캠페인 KPI 컬럼 초안, 담당자 확정 필요")
def campaign_kpi():
    # 주간 집계와 담당 코드에 필요한 보상 및 참여 이력 연결 → 캠페인 지표 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(CAMPAIGN_KPI_DRAFT_SCHEMA, "weekly_user_profile", "weekly_gold")


@dp.materialized_view(schema=WEEKLY_OUTPUTS_DRAFT_SCHEMA, comment="계산 미연결. 최종 묶음 컬럼 초안, 소비 계약 확정 필요")
def weekly_outputs_gold():
    # 결과별 컬럼과 저장 테이블 지정. 서로 다른 결과를 합칠지 별도 저장할지 연결 시 결정
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(WEEKLY_OUTPUTS_DRAFT_SCHEMA, "weekly_gold", "baseline_gold", "weekly_user_profile",
                   "next_week_missions", "ranking", "campaign_kpi")


# 앞의 세 단계에서만 사용. 이후 담당자 블록과 분리
# 원본: build_weekly_summary.py
# 파이프라인 연결: 검증용 count/collect 대신 Spark 표현식 사용
# null mode 판정은 창연님 수정 d268a7d 기준
def calculate_weekly(trips):
    # 주차 경계는 한국시간 월요일. Spark 세션 시간대는 UTC 기준
    if spark.conf.get("spark.sql.session.timeZone") not in {"UTC", "Etc/UTC"}:
        raise ValueError("파이프라인 설정 spark.sql.session.timeZone=UTC 필요")
    valid = (
        F.col("trip_id").isNotNull() & F.col("user_id").isNotNull()
        & F.col("campaign_id").isNotNull()
        & F.to_timestamp("ended_at").isNotNull()
        & (F.col("carbon.unit") == "kgCO2e")
        & F.col("carbon.policy_version").isNotNull()
        & F.col("carbon.factor_version").isNotNull()
        & (F.col("carbon.kg_co2e") >= 0)
        & (F.col("carbon.kg_co2e") < F.lit(float("inf")))
        & (F.size("segments") > 0)
        & F.forall("segments", lambda segment:
            (segment.carbon_kg >= 0) & (segment.carbon_kg < F.lit(float("inf")))
            & (segment.distance_m >= 0) & (segment.distance_m < F.lit(float("inf")))))
    # 누락값이나 잘못된 탄소 단위 발견 시 집계 실패. 조용한 제외나 0 보정 금지
    trips = trips.filter(F.when(F.coalesce(valid, F.lit(False)), F.lit(True)).otherwise(
        F.raise_error("Final Trip 필수값, 거리, 탄소 단위 확인 필요").cast("boolean")))
    local = trips.withColumn("ended_at", F.from_utc_timestamp(F.to_timestamp("ended_at"), "Asia/Seoul"))
    weekly = assign_week(local)
    window = Window.partitionBy("campaign_id", "week")
    version = F.struct(F.col("carbon.policy_version"), F.col("carbon.factor_version"))
    weekly = weekly.withColumn("_min_version", F.min(version).over(window)).withColumn(
        "_max_version", F.max(version).over(window))
    weekly = weekly.filter(F.when(F.col("_min_version") == F.col("_max_version"), F.lit(True)).otherwise(
        F.raise_error("동일 캠페인과 주차 내 탄소 정책 버전 혼합").cast("boolean")))
    return build_personal_weekly(weekly.drop("_min_version", "_max_version"))

def assign_week(df):
    trip_date = F.to_date('ended_at')
    iso_day = F.pmod(F.dayofweek(trip_date) + F.lit(5), F.lit(7)) + F.lit(1)
    iso_thursday = F.date_add(trip_date, F.lit(4) - iso_day)
    return df.withColumn('trip_date', trip_date).withColumn('iso_year', F.year(iso_thursday)).withColumn('iso_week', F.weekofyear(trip_date)).withColumn('week', F.concat(F.col('iso_year').cast('string'), F.lit('-W'), F.lpad(F.col('iso_week').cast('string'), 2, '0')))

def explode_segments(df):
    exploded = df.select('trip_id', 'user_id', 'campaign_id', 'week', F.col('carbon.policy_version').alias('carbon_policy_version'), F.col('carbon.factor_version').alias('factor_version'), F.explode('segments').alias('segment'))
    return exploded.withColumn('effective_mode', F.lower(F.col('segment.model_prediction'))).withColumn('distance_m', F.col('segment.distance_m').cast('double')).withColumn('segment_kg_co2e', F.col('segment.carbon_kg').cast('double'))

def compute_mode_metrics(exploded_df):
    per_mode = exploded_df.groupBy('user_id', 'campaign_id', 'week', 'effective_mode').agg(F.countDistinct('trip_id').alias('mode_trip_count'), F.sum('distance_m').alias('distance_m'), F.sum('segment_kg_co2e').alias('kg_co2e'))
    totals = exploded_df.groupBy('user_id', 'campaign_id', 'week').agg(F.countDistinct('trip_id').alias('total_trip_count'), F.sum('distance_m').alias('total_distance_m'), F.sum('segment_kg_co2e').alias('total_segment_kg_co2e'))
    joined = per_mode.join(totals, ['user_id', 'campaign_id', 'week'])
    return joined.withColumn('mode_trip_ratio', F.col('mode_trip_count') / F.col('total_trip_count')).withColumn('mode_distance_ratio', F.try_divide(F.col('distance_m'), F.col('total_distance_m'))).withColumn('mode_carbon_ratio', F.when(F.col('total_segment_kg_co2e') > 0, F.col('kg_co2e') / F.col('total_segment_kg_co2e')).otherwise(F.lit(0.0)))

def compute_trip_primary_facts(exploded_df):
    keys = ['trip_id', 'user_id', 'campaign_id', 'week']
    invalid_segment = F.col('effective_mode').isNull() | ~F.col('effective_mode').isin(MODES) | F.col('distance_m').isNull() | (F.col('distance_m') <= 0)
    quality = exploded_df.groupBy(*keys).agg(F.sum(F.when(invalid_segment, 1).otherwise(0)).alias('invalid_segment_count'), F.sum(F.when(~invalid_segment, F.col('distance_m')).otherwise(F.lit(0.0))).alias('trip_distance_m'))
    valid_segments = exploded_df.filter(~invalid_segment)
    per_trip_mode = valid_segments.groupBy(*keys, 'effective_mode').agg(F.sum('distance_m').alias('mode_distance_m'))
    w = Window.partitionBy(*keys)
    ranked = per_trip_mode.withColumn('max_mode_distance_m', F.max('mode_distance_m').over(w)).withColumn('is_primary_winner', F.when(F.abs(F.col('mode_distance_m') - F.col('max_mode_distance_m')) < F.lit(1e-09), F.lit(1)).otherwise(F.lit(0)))
    mode_summary = ranked.groupBy(*keys).agg(F.sum('is_primary_winner').alias('primary_winner_count'), F.first(F.when(F.col('is_primary_winner') == 1, F.col('effective_mode')), ignorenulls=True).alias('primary_mode_candidate'))
    result = quality.join(mode_summary, keys, 'left').fillna(0, subset=['primary_winner_count']).withColumn('primary_mode_invalid_reason', F.when(F.col('invalid_segment_count') > 0, F.lit('invalid_segment')).when(F.col('primary_winner_count') != 1, F.lit('primary_mode_tie'))).withColumn('primary_mode', F.when(F.col('primary_mode_invalid_reason').isNull(), F.col('primary_mode_candidate'))).withColumn('primary_mode_valid', F.col('primary_mode_invalid_reason').isNull()).drop('primary_mode_candidate')
    return result

def aggregate_primary_facts(primary_trip_df):
    return primary_trip_df.groupBy('user_id', 'campaign_id', 'week').agg(F.sum(F.when(F.col('primary_mode_valid'), 1).otherwise(0)).cast('long').alias('valid_primary_trip_count'), F.sum(F.when(~F.col('primary_mode_valid'), 1).otherwise(0)).cast('long').alias('invalid_primary_trip_count'), F.sum(F.when(F.col('primary_mode_invalid_reason') == 'primary_mode_tie', 1).otherwise(0)).cast('long').alias('ambiguous_primary_trip_count'), F.sum(F.when(F.col('primary_mode_invalid_reason') == 'invalid_segment', 1).otherwise(0)).cast('long').alias('invalid_segment_primary_trip_count'), F.sum(F.when(F.col('primary_mode') == 'car', 1).otherwise(0)).cast('long').alias('car_primary_trip_count'), F.sum(F.when(F.col('primary_mode').isin(TRANSIT_MODES), 1).otherwise(0)).cast('long').alias('transit_primary_trip_count'), F.sum(F.when(F.col('primary_mode').isin(LOW_CARBON_MODES), 1).otherwise(0)).cast('long').alias('low_carbon_trip_count'), F.sum(F.when((F.col('primary_mode') == 'car') & (F.col('trip_distance_m') <= F.lit(SHORT_CAR_MAX_DISTANCE_M)), 1).otherwise(0)).cast('long').alias('short_car_trip_count')).withColumn('car_primary_ratio', F.when(F.col('valid_primary_trip_count') > 0, F.col('car_primary_trip_count') / F.col('valid_primary_trip_count'))).withColumn('short_car_share', F.when(F.col('car_primary_trip_count') > 0, F.col('short_car_trip_count') / F.col('car_primary_trip_count')))

def _pivot_ratio(mode_metrics_df, ratio_col, prefix):
    pivoted = mode_metrics_df.groupBy('user_id', 'campaign_id', 'week').pivot('effective_mode', MODES).agg(F.first(ratio_col))
    for mode in MODES:
        name = f'{prefix}_{mode}'
        pivoted = pivoted.withColumnRenamed(mode, name).fillna(0.0, subset=[name])
    return pivoted

def _pivot_mode_distance(mode_metrics_df):
    pivoted = mode_metrics_df.groupBy('user_id', 'campaign_id', 'week').pivot('effective_mode', MODES).agg(F.first('distance_m'))
    for mode in MODES:
        name = f'{mode}_distance_m'
        pivoted = pivoted.withColumnRenamed(mode, name).fillna(0.0, subset=[name])
    return pivoted

def build_personal_weekly(ready_df):
    exploded = explode_segments(ready_df)
    mode_metrics = compute_mode_metrics(exploded)
    mode_distance_pivot = _pivot_mode_distance(mode_metrics)
    trip_ratio_pivot = _pivot_ratio(mode_metrics, 'mode_trip_ratio', 'mode_trip_ratio')
    distance_ratio_pivot = _pivot_ratio(mode_metrics, 'mode_distance_ratio', 'mode_distance_ratio')
    carbon_ratio_pivot = _pivot_ratio(mode_metrics, 'mode_carbon_ratio', 'mode_carbon_ratio')
    primary_facts = aggregate_primary_facts(compute_trip_primary_facts(exploded))
    trip_agg = ready_df.groupBy('user_id', 'campaign_id', 'week').agg(F.countDistinct('trip_id').alias('trip_count'), F.sum('carbon.kg_co2e').alias('total_kg_co2e'), F.first('carbon.policy_version').alias('carbon_policy_version'), F.first('carbon.factor_version').alias('factor_version'))
    distance_agg = exploded.groupBy('user_id', 'campaign_id', 'week').agg(F.sum('distance_m').alias('total_distance_m'))
    return trip_agg.join(distance_agg, ['user_id', 'campaign_id', 'week']).join(mode_distance_pivot, ['user_id', 'campaign_id', 'week']).join(trip_ratio_pivot, ['user_id', 'campaign_id', 'week']).join(distance_ratio_pivot, ['user_id', 'campaign_id', 'week']).join(carbon_ratio_pivot, ['user_id', 'campaign_id', 'week']).join(primary_facts, ['user_id', 'campaign_id', 'week'], 'left')
