"""주간 분석 파이프라인 초기 뼈대.

전체 블록은 컬럼과 연결 관계만 정의한 0행 결과 반환. 실제 조회 및 계산 코드 없음.
각 블록의 empty_result(...) 부분을 담당자의 계산 코드와 결과 DataFrame 반환으로 교체.
입력 테이블 조회 → 계산 → 결과 DataFrame 반환 순서로 작성.
함수 내부에서 직접 저장, Cosmos 호출, 다른 Job 실행 제외.
테이블 생성과 갱신은 파이프라인에서 처리. Cosmos 반영은 바깥 Job의 후속 작업.
미구현 블록도 실제 출력 컬럼을 가진 0행 결과 반환. 컬럼 초안은 블록 설명에 표시.
가입 정보, 미션 응답 이력, 실제 보상 이력 등 외부 입력은 담당 코드 연결 시 추가.
실행 시작: 바깥 Job의 run_weekly_pipeline. 데이터 입력 시작: final_trip_gold_input().
"""
from pyspark import pipelines as dp
from pyspark.sql import SparkSession, functions as F

spark = SparkSession.builder.getOrCreate()
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
# 원본: baseline_eligibility.py, Hayden Shin 작성
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


@dp.temporary_view(comment="조회 미연결. 최종 Trip Gold 입력 코드 작성 위치")
def final_trip_gold_input():
    # 여기에 최종 Trip Delta 조회 코드 입력. Cosmos 조회 제외
    # 캠페인과 집계 기간 조건 적용 후 FINAL_TRIP_SCHEMA 형식으로 반환
    return empty_result(FINAL_TRIP_SCHEMA)


@dp.temporary_view(comment="계산 미연결. 사용자별 주간 집계 코드 작성 위치")
def weekly_summary():
    # 참고: build_weekly_summary.py, 5dt028 작성 / ManiaKCY 수정
    # final_trip_gold_input 입력 → 사용자별 주간 집계 → WEEKLY_SCHEMA 형식으로 반환
    # 거리 m, 탄소 kgCO2e. 아래 빈 결과를 담당 계산 결과로 교체
    return empty_result(WEEKLY_SCHEMA, "final_trip_gold_input")


@dp.materialized_view(schema=WEEKLY_SCHEMA, comment="계산 미연결. 주간 집계 결과 저장 코드 작성 위치")
def weekly_gold():
    # weekly_summary 입력 → 저장할 결과 컬럼 선택 → WEEKLY_SCHEMA 형식으로 반환
    return empty_result(WEEKLY_SCHEMA, "weekly_summary")


@dp.temporary_view(comment="Baseline 계산 대상 판정 코드 입력 위치")
def baseline_eligibility():
    # 주간 이력과 가입 정보 입력 → 수집 기간과 Trip 수 조건 판정 → 사용자별 판정 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(PERSONAL_ELIGIBILITY_SCHEMA, "weekly_gold")


@dp.temporary_view(comment="개인 Baseline 계산 및 갱신 코드 입력 위치")
def personal_baseline():
    # 주간 이력과 대상 판정 입력 → 기존 개인 Baseline 계산 코드 적용 → 사용자별 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(PERSONAL_SCHEMA, "baseline_eligibility")


@dp.temporary_view(comment="개인 Baseline 준비 완료 사용자 선택 위치")
def personal_ready_users():
    # 개인 Baseline 입력 → 준비 완료 조건 필터 → 대상 사용자 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(PERSONAL_SCHEMA, "personal_baseline")


@dp.temporary_view(comment="Global Baseline 계산 가능 여부 판정 위치")
def global_eligibility():
    # 대상 사용자 입력 → 참여 인원 등 정책 조건 판정 → 캠페인별 판정 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(GLOBAL_ELIGIBILITY_SCHEMA, "personal_ready_users")


@dp.temporary_view(comment="Global Baseline 계산 및 갱신 코드 입력 위치")
def global_baseline():
    # 개인 Baseline과 대상 판정 입력 → 기존 Global 계산 코드 적용 → 캠페인별 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return empty_result(GLOBAL_SCHEMA, "global_eligibility")


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
