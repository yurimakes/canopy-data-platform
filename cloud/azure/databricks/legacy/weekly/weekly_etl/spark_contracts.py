"""Pure declarations extracted from validated Weekly Spark transforms; no Lakeflow registration."""

from pyspark.sql import SparkSession, Window, functions as F, types as T

MODES = ["walk", "bike", "car", "bus", "rail"]

LOW_CARBON_MODES = ["walk", "bike", "bus", "rail"]

TRANSIT_MODES = ["bus", "rail"]

SHORT_CAR_MAX_DISTANCE_M = 2000.0

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

PERSONAL_ELIGIBILITY_SCHEMA = """
    user_id STRING, campaign_id STRING, week STRING,
    status STRING, policy_version STRING, observation_days BIGINT,
    confirmed_trip_count BIGINT, observation_source STRING,
    reasons ARRAY<STRING>
"""

GLOBAL_ELIGIBILITY_SCHEMA = """
    campaign_id STRING, week STRING, status STRING,
    policy_version STRING, eligible_participant_count BIGINT
"""

BEHAVIOR_DRAFT_SCHEMA = """
    user_id STRING, campaign_id STRING, week STRING,
    before_week_start STRING, before_week_end STRING,
    after_week_start STRING, after_week_end STRING,
    before_avg_weekly_kg_co2e DOUBLE, after_avg_weekly_kg_co2e DOUBLE,
    change_kg_co2e DOUBLE, change_rate DOUBLE,
    status STRING, reason STRING, policy_version STRING
"""

REWARD_CALC_SCHEMA = """
    user_id STRING, campaign_id STRING, week STRING,
    status STRING, payable BOOLEAN, points DOUBLE,
    reason STRING, point_reason STRING,
    missions_completed_this_week BIGINT, policy_version STRING
"""

RANKING_DRAFT_SCHEMA = """
    campaign_id STRING, week STRING, ranking_type STRING,
    user_id STRING, department_id STRING,
    reward_points DOUBLE, rank BIGINT,
    policy_version STRING, generated_at TIMESTAMP
"""

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

def calculate_weekly(trips):
    spark = SparkSession.getActiveSession()
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
    local = trips.withColumn("ended_at", F.from_utc_timestamp(F.to_timestamp(F.coalesce(F.col("started_at"), F.col("ended_at"))), "Asia/Seoul"))
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
    return joined.withColumn('mode_trip_ratio', F.try_divide(F.col('mode_trip_count'), F.col('total_trip_count'))).withColumn('mode_distance_ratio', F.try_divide(F.col('distance_m'), F.col('total_distance_m'))).withColumn('mode_carbon_ratio', F.when(F.col('total_segment_kg_co2e') > 0, F.try_divide(F.col('kg_co2e'), F.col('total_segment_kg_co2e'))).otherwise(F.lit(0.0)))

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
    return primary_trip_df.groupBy('user_id', 'campaign_id', 'week').agg(F.sum(F.when(F.col('primary_mode_valid'), 1).otherwise(0)).cast('long').alias('valid_primary_trip_count'), F.sum(F.when(~F.col('primary_mode_valid'), 1).otherwise(0)).cast('long').alias('invalid_primary_trip_count'), F.sum(F.when(F.col('primary_mode_invalid_reason') == 'primary_mode_tie', 1).otherwise(0)).cast('long').alias('ambiguous_primary_trip_count'), F.sum(F.when(F.col('primary_mode_invalid_reason') == 'invalid_segment', 1).otherwise(0)).cast('long').alias('invalid_segment_primary_trip_count'), F.sum(F.when(F.col('primary_mode') == 'car', 1).otherwise(0)).cast('long').alias('car_primary_trip_count'), F.sum(F.when(F.col('primary_mode').isin(TRANSIT_MODES), 1).otherwise(0)).cast('long').alias('transit_primary_trip_count'), F.sum(F.when(F.col('primary_mode').isin(LOW_CARBON_MODES), 1).otherwise(0)).cast('long').alias('low_carbon_trip_count'), F.sum(F.when((F.col('primary_mode') == 'car') & (F.col('trip_distance_m') <= F.lit(SHORT_CAR_MAX_DISTANCE_M)), 1).otherwise(0)).cast('long').alias('short_car_trip_count')).withColumn('car_primary_ratio', F.when(F.col('valid_primary_trip_count') > 0, F.try_divide(F.col('car_primary_trip_count'), F.col('valid_primary_trip_count')))).withColumn('short_car_share', F.when(F.col('car_primary_trip_count') > 0, F.try_divide(F.col('short_car_trip_count'), F.col('car_primary_trip_count'))))

def _pivot_ratio(mode_metrics_df, ratio_col, prefix):
    keys = ['user_id', 'campaign_id', 'week']

    expressions = [
        F.max(
            F.when(
                F.col('effective_mode') == mode,
                F.col(ratio_col),
            )
        ).alias(f'{prefix}_{mode}')
        for mode in MODES
    ]

    result = mode_metrics_df.groupBy(*keys).agg(*expressions)

    return result.fillna(
        0.0,
        subset=[f'{prefix}_{mode}' for mode in MODES],
    )

def _pivot_mode_distance(mode_metrics_df):
    keys = ['user_id', 'campaign_id', 'week']

    expressions = [
        F.max(
            F.when(
                F.col('effective_mode') == mode,
                F.col('distance_m'),
            )
        ).alias(f'{mode}_distance_m')
        for mode in MODES
    ]

    result = mode_metrics_df.groupBy(*keys).agg(*expressions)

    return result.fillna(
        0.0,
        subset=[f'{mode}_distance_m' for mode in MODES],
    )

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


def mission_kpi_input(frame):
    """Adapt Mission's exclusive Monday end to the team's inclusive KPI boundary.

    Keep the published Mission Response contract unchanged; only the KPI input
    uses the final included calendar date (Sunday).
    """
    from pyspark.sql import functions as F
    return frame.withColumn('week_end', F.date_sub(F.to_date('week_end'), 1))
