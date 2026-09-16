"""주간 분석 파이프라인 초기 뼈대.

최종 Trip 입력 → 주간 집계 → weekly_gold 연결. 나머지 블록은 빈 결과 반환.
현재 입력은 개발용 Final Trip 경로. 운영 출퇴근 데이터 연결 전 테스트 용도.
각 블록의 pending(...) 부분을 담당자의 계산 코드와 결과 DataFrame 반환으로 교체.
입력 테이블 조회 → 계산 → 결과 DataFrame 반환 순서로 작성.
함수 내부에서 직접 저장, Cosmos 호출, 다른 Job 실행 제외.
테이블 생성과 갱신은 파이프라인에서 처리. Cosmos 반영은 바깥 Job의 후속 작업.
SCAFFOLD 컬럼은 미구현 블록에서만 사용. 주간 결과는 기존 Weekly Gold 컬럼으로 반환.
현재 연결선은 초기 구상 기준. 담당 코드 연결 시 필요한 입력 테이블 재확인.
"""
from pyspark import pipelines as dp
from pyspark.sql import SparkSession, Window, functions as F

spark = SparkSession.builder.getOrCreate()
SCAFFOLD_SCHEMA = "_scaffold_stage string, _implementation_status string"
SCAFFOLD_PROPERTIES = {"canopy.implementation_status": "scaffold"}


def pending(stage, *parents):
    """실제 계산 없이 앞 단계와의 연결만 표시하는 빈 데이터 반환."""
    frames = [spark.read.table(parent).limit(0).select(
        F.lit(stage).alias("_scaffold_stage"),
        F.lit("not_implemented").alias("_implementation_status"),
    ) for parent in parents]
    frame = frames[0]
    for parent in frames[1:]:
        frame = frame.unionByName(parent)
    return frame


# 개발용 최종 Trip Delta 경로. 운영 입력은 별도 확인 후 변경
FINAL_TRIP_PATH = "abfss://curated@stcanopydev5dt.dfs.core.windows.net/pipeline_test/trip_finalization/iphone_final_trips"
MODES = ["walk", "bike", "car", "bus", "rail"]
LOW_CARBON_MODES = ["walk", "bike", "bus", "rail"]
TRANSIT_MODES = ["bus", "rail"]
SHORT_CAR_MAX_DISTANCE_M = 2000.0


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
    # 원본: build_weekly_summary.py, 5dt028 작성 / ManiaKCY 수정
    # 입력: final_trip_gold_input / 출력: shared/schemas/baseline/weekly_user_gold.schema.json
    # 거리 m, 탄소 kgCO2e. 저장된 탄소 합계 사용, 배출계수 재계산 제외
    return calculate_weekly(spark.read.table("final_trip_gold_input"))


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


@dp.materialized_view(comment="개발용 주간 집계 결과. 사용자, 캠페인, 주차별 한 행")
def weekly_gold():
    # 계산 결과 저장. 실제 출력 컬럼 유지
    return spark.read.table("weekly_summary")


@dp.temporary_view(comment="Baseline 계산 대상 판정 코드 입력 위치")
def baseline_eligibility():
    # 주간 이력과 가입 정보 입력 → 수집 기간과 Trip 수 조건 판정 → 사용자별 판정 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("baseline_eligibility", "weekly_gold")


@dp.temporary_view(comment="개인 Baseline 계산 및 갱신 코드 입력 위치")
def personal_baseline():
    # 주간 이력과 대상 판정 입력 → 기존 개인 Baseline 계산 코드 적용 → 사용자별 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("personal_baseline", "baseline_eligibility")


@dp.temporary_view(comment="개인 Baseline 준비 완료 사용자 선택 위치")
def personal_ready_users():
    # 개인 Baseline 입력 → 준비 완료 조건 필터 → 대상 사용자 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("personal_ready_users", "personal_baseline")


@dp.temporary_view(comment="Global Baseline 계산 가능 여부 판정 위치")
def global_eligibility():
    # 대상 사용자 입력 → 참여 인원 등 정책 조건 판정 → 캠페인별 판정 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("global_eligibility", "personal_ready_users")


@dp.temporary_view(comment="Global Baseline 계산 및 갱신 코드 입력 위치")
def global_baseline():
    # 개인 Baseline과 대상 판정 입력 → 기존 Global 계산 코드 적용 → 캠페인별 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("global_baseline", "global_eligibility")


@dp.materialized_view(comment="Baseline 결과 테이블 저장 위치", table_properties=SCAFFOLD_PROPERTIES)
def baseline_gold():
    # 개인 결과와 Global 결과의 저장 형식 지정. 서로 다른 컬럼의 단순 합치기 제외
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("baseline_gold", "personal_baseline", "global_baseline")


@dp.temporary_view(comment="행동 변화 계산 코드 입력 위치")
def behavior_change():
    # 담당 코드에서 필요한 주간 이력, Baseline, 미션 이력 연결 → 행동 변화 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("behavior_change", "weekly_gold", "baseline_gold")


@dp.temporary_view(comment="주간 사용자 프로필 생성 코드 입력 위치")
def weekly_user_profile():
    # 주간 집계와 미션 응답 이력 연결 → 사용자 프로필 반환. 초기 연결선은 담당 코드 기준으로 조정
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("weekly_user_profile", "weekly_gold", "behavior_change")


@dp.materialized_view(comment="다음 주 미션 선정 코드 입력 위치", table_properties=SCAFFOLD_PROPERTIES)
def next_week_missions():
    # 사용자 프로필과 미션 정책 입력 → 다음 주 미션 결과 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("next_week_missions", "weekly_user_profile")


@dp.materialized_view(comment="랭킹 집계 코드 입력 위치", table_properties=SCAFFOLD_PROPERTIES)
def ranking():
    # 실제 보상 지급 이력과 소속 정보 연결 → 사용자 및 부서별 랭킹 반환. 초기 연결선 조정 필요
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("ranking", "weekly_user_profile")


@dp.materialized_view(comment="캠페인 지표 집계 코드 입력 위치", table_properties=SCAFFOLD_PROPERTIES)
def campaign_kpi():
    # 주간 집계와 담당 코드에 필요한 보상 및 참여 이력 연결 → 캠페인 지표 반환
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("campaign_kpi", "weekly_user_profile", "weekly_gold")


@dp.materialized_view(comment="주간 분석 결과 저장 경계. 실제 출력 형식 연결 전",
                      table_properties=SCAFFOLD_PROPERTIES)
def weekly_outputs_gold():
    # 결과별 컬럼과 저장 테이블 지정. 서로 다른 결과를 합칠지 별도 저장할지 연결 시 결정
    # 아래 빈 결과 반환 부분을 계산 코드와 return 결과로 교체
    return pending("weekly_outputs_gold", "weekly_gold", "baseline_gold", "weekly_user_profile",
                   "next_week_missions", "ranking", "campaign_kpi")


# 주간 집계 계산부. 기존 주간 집계 공식 재사용
# 원본: cloud/azure/pipelines/databricks/build_weekly_summary.py
# 기존 연동 코드에서 검증용 count/collect 제거, 0거리 나눗셈 처리
# null mode는 invalid_segment 판정. 팀원 수정 d268a7d 기준. 원본 파일 변경 없음
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
    w = Window.partitionBy('trip_id')
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
