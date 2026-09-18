"""Spark transformations for CANOPY Personal and Global Baseline.

Lakeflow table/view declarations remain in weekly_pipeline.py.

This module only transforms Spark DataFrames.
It does not:
- declare Lakeflow tables/views
- write Delta tables
- call Cosmos DB
- trigger another job
"""

from __future__ import annotations

from pyspark.sql import DataFrame, Window, functions as F


def build_personal_baseline(
    weekly: DataFrame,
    eligibility: DataFrame,
    *,
    baseline_policy_version: str,
    commute_scope_verified: bool,
    eligibility_policy: dict,
) -> DataFrame:
    """Build Personal Baseline from previously completed weekly history."""

    # 현재 주는 제외하고 이전 완료 주까지만 누적
    prior_window = (
        Window
        .partitionBy("user_id", "campaign_id")
        .orderBy("week")
        .rowsBetween(Window.unboundedPreceding, -1)
    )

    accumulated = (
        weekly
        .withColumn(
            "cumulative_g_co2e",
            F.sum(
                F.col("total_kg_co2e") * F.lit(1000.0)
            ).over(prior_window),
        )
        .withColumn(
            "cumulative_distance_km",
            F.sum(
                F.col("total_distance_m") / F.lit(1000.0)
            ).over(prior_window),
        )
    )

    joined = (
        accumulated.alias("w")
        .join(
            eligibility.alias("e"),
            ["user_id", "campaign_id", "week"],
            "left",
        )
    )

    # 이전 완료 주 누적 탄소가 정상적인 값인지 확인
    valid_g = (
        F.col("cumulative_g_co2e").isNotNull()
        & ~F.isnan("cumulative_g_co2e")
        & (F.col("cumulative_g_co2e") >= 0)
        & (F.col("cumulative_g_co2e") < float("inf"))
    )

    # 이전 완료 주 누적 거리가 정상이고 0보다 큰지 확인
    valid_km = (
        F.col("cumulative_distance_km").isNotNull()
        & ~F.isnan("cumulative_distance_km")
        & (F.col("cumulative_distance_km") > 0)
        & (F.col("cumulative_distance_km") < float("inf"))
    )

    personal_ready_status = eligibility_policy["personal"]["status"][
        "when_eligible"
    ]
    personal_collecting_status = eligibility_policy["personal"]["status"][
        "before_eligible"
    ]
    cold_start_primary = eligibility_policy["personal"]["cold_start"][
        "primary_baseline"
    ]

    # Personal Baseline 계산 전 기본 gate
    calculation_gate = (
        (F.col("e.status") == personal_ready_status)
        & valid_g
        & valid_km
        & F.lit(commute_scope_verified)
    )

    # 기존 Personal 공식:
    # 이전 완료 주까지 누적 탄소(gCO2e) / 누적 거리(km)
    calculated_baseline = F.try_divide(
        F.col("cumulative_g_co2e"),
        F.col("cumulative_distance_km"),
    )

    valid_calculated_baseline = (
        calculated_baseline.isNotNull()
        & ~F.isnan(calculated_baseline)
        & (calculated_baseline >= 0)
        & (calculated_baseline < float("inf"))
    )

    # 계산 결과 자체까지 정상이어야 최종 Personal ready
    can_compute = (
        calculation_gate
        & valid_calculated_baseline
    )

    baseline_value = (
        F.when(
            can_compute,
            calculated_baseline,
        )
        .otherwise(F.lit(None).cast("double"))
    )

    # Eligibility 블록에서 전달받은 사유
    base_reasons = F.coalesce(
        F.col("e.reasons"),
        F.expr("array()").cast("array<string>"),
    )

    # 출퇴근 범위가 아직 확인되지 않은 경우 canonical reason 추가
    reasons_with_scope = (
        F.when(
            ~F.lit(commute_scope_verified),
            F.array_union(
                base_reasons,
                F.array(F.lit("weekly_commute_scope_unverified")),
            ),
        )
        .otherwise(base_reasons)
    )

    # 계산 gate는 통과했지만 실제 계산값이 비정상인 경우
    final_reasons = (
        F.when(
            calculation_gate & ~valid_calculated_baseline,
            F.array_union(
                reasons_with_scope,
                F.array(F.lit("invalid_calculated_value")),
            ),
        )
        .otherwise(reasons_with_scope)
    )

    eligibility_reason = (
        F.when(
            F.size(final_reasons) > 0,
            F.concat_ws(",", final_reasons),
        )
        .otherwise(F.lit(None).cast("string"))
    )

    return joined.select(
        "user_id",
        "campaign_id",
        "week",

        F.col("cumulative_g_co2e")
        .cast("double")
        .alias("cumulative_g_co2e"),

        F.col("cumulative_distance_km")
        .cast("double")
        .alias("cumulative_distance_km"),

        baseline_value.alias("baseline_g_co2e_per_km"),

        F.when(
            can_compute,
            F.lit("personal_cumulative"),
        )
        .otherwise(F.lit("population_fallback"))
        .alias("method"),

        F.lit(baseline_policy_version)
        .alias("policy_version"),

        F.when(
            can_compute,
            F.lit(personal_ready_status),
        )
        .otherwise(F.lit(personal_collecting_status))
        .alias("status"),

        baseline_value.alias("value"),

        F.col("e.policy_version")
        .alias("eligibility_policy_version"),

        F.col("e.observation_days")
        .cast("long")
        .alias("observation_days"),

        F.col("e.confirmed_trip_count")
        .cast("long")
        .alias("confirmed_trip_count"),

        F.col("e.observation_source")
        .cast("string")
        .alias("observation_source"),

        eligibility_reason.alias("eligibility_reason"),

        F.when(
            can_compute,
            F.lit(None).cast("string"),
        )
        .otherwise(F.lit(cold_start_primary))
        .alias("primary_baseline"),
    )


def select_personal_ready_users(
    personal: DataFrame,
    *,
    eligibility_policy: dict,
) -> DataFrame:
    """Select valid Personal snapshots that may participate in Global Baseline."""

    required_personal_status = eligibility_policy["global"][
        "participant_rule"
    ]["require_personal_status"]

    return personal.filter(
        # Global 정책이 요구하는 Personal 상태
        (F.col("status") == required_personal_status)

        # 현재 Eligibility 정책 버전으로 판정된 결과만 사용
        & (
            F.col("eligibility_policy_version")
            == eligibility_policy["policy_version"]
        )

        # Population fallback 제외
        & (F.col("method") == "personal_cumulative")

        # 정상 user_id만 사용
        & F.col("user_id").isNotNull()
        & (F.length(F.trim(F.col("user_id"))) > 0)

        # 정상 Personal Baseline 값만 사용
        & F.col("baseline_g_co2e_per_km").isNotNull()
        & ~F.isnan("baseline_g_co2e_per_km")
        & (F.col("baseline_g_co2e_per_km") >= 0)
        & (F.col("baseline_g_co2e_per_km") < float("inf"))
    )


def build_global_eligibility(
    personal: DataFrame,
    ready: DataFrame,
    *,
    eligibility_policy: dict,
) -> DataFrame:
    """Evaluate whether each campaign/week has enough valid participants."""

    keys = ["campaign_id", "week"]

    # Personal 결과가 존재하는 모든 campaign/week를 판정 대상으로 유지.
    # ready 사용자가 0명이어도 collecting 행은 반환되어야 함.
    scopes = (
        personal
        .select(*keys)
        .filter(
            F.col("campaign_id").isNotNull()
            & F.col("week").isNotNull()
        )
        .distinct()
    )

    # canonical Global 코드와 동일하게
    # user/campaign/week당 Personal snapshot 중복을 허용하지 않음.
    snapshot_counts = (
        ready
        .groupBy(
            "campaign_id",
            "week",
            "user_id",
        )
        .agg(
            F.count("*").alias("_snapshot_count")
        )
    )

    checked_snapshots = snapshot_counts.filter(
        F.when(
            F.col("_snapshot_count") == 1,
            F.lit(True),
        ).otherwise(
            F.raise_error(
                "Duplicate Personal snapshot for user/campaign/week"
            ).cast("boolean")
        )
    )

    participant_counts = (
        checked_snapshots
        .groupBy(*keys)
        .agg(
            F.count("*")
            .cast("long")
            .alias("eligible_participant_count")
        )
    )

    scoped = (
        scopes
        .join(
            participant_counts,
            keys,
            "left",
        )
        .withColumn(
            "eligible_participant_count",
            F.coalesce(
                F.col("eligible_participant_count"),
                F.lit(0).cast("long"),
            ),
        )
    )

    minimum_participants = int(
        eligibility_policy["global"][
            "minimum_eligible_participants"
        ]
    )

    ready_status = eligibility_policy["global"]["status"][
        "when_eligible"
    ]
    collecting_status = eligibility_policy["global"]["status"][
        "below_minimum_participants"
    ]

    return scoped.select(
        "campaign_id",
        "week",

        F.when(
            F.col("eligible_participant_count")
            >= F.lit(minimum_participants),
            F.lit(ready_status),
        )
        .otherwise(F.lit(collecting_status))
        .alias("status"),

        F.lit(eligibility_policy["policy_version"])
        .alias("policy_version"),

        F.col("eligible_participant_count")
        .cast("long")
        .alias("eligible_participant_count"),
    )


def build_global_baseline(
    ready: DataFrame,
    eligibility: DataFrame,
    *,
    baseline_policy_version: str,
    eligibility_policy: dict,
) -> DataFrame:
    """Build equal-user Global Baseline after the Global eligibility gate."""

    keys = ["campaign_id", "week"]

    # Global eligibility 결과 컬럼을 명시적으로 내부 이름으로 분리.
    eligibility_scoped = eligibility.select(
        "campaign_id",
        "week",

        F.col("status")
        .alias("_global_eligibility_status"),

        F.col("policy_version")
        .alias("_eligibility_policy_version"),

        F.col("eligible_participant_count")
        .cast("long")
        .alias("eligible_participant_count"),
    )

    # canonical 공식:
    # 유효한 Personal Baseline들의 동일 사용자 가중 평균
    aggregates = (
        ready
        .groupBy(*keys)
        .agg(
            F.count("*")
            .cast("long")
            .alias("_valid_participant_count"),

            F.sum("baseline_g_co2e_per_km")
            .cast("double")
            .alias("_sum_baseline_g_co2e_per_km"),
        )
    )

    joined = (
        eligibility_scoped
        .join(
            aggregates,
            keys,
            "left",
        )
        .withColumn(
            "_valid_participant_count",
            F.coalesce(
                F.col("_valid_participant_count"),
                F.lit(0).cast("long"),
            ),
        )
    )

    # Eligibility 판정 시 계산한 사용자 수와
    # 실제 Global 계산 입력 사용자 수가 반드시 같아야 함.
    checked = joined.filter(
        F.when(
            F.col("_valid_participant_count")
            == F.col("eligible_participant_count"),
            F.lit(True),
        ).otherwise(
            F.raise_error(
                "Global eligibility participant count mismatch"
            ).cast("boolean")
        )
    )

    ready_status = eligibility_policy["global"]["status"][
        "when_eligible"
    ]

    baseline_value = (
        F.when(
            (
                F.col("_global_eligibility_status")
                == ready_status
            )
            & (F.col("_valid_participant_count") > 0),
            F.try_divide(
                F.col("_sum_baseline_g_co2e_per_km"),
                F.col("_valid_participant_count"),
            ),
        )
        .otherwise(F.lit(None).cast("double"))
    )

    return checked.select(
        "campaign_id",
        "week",

        F.col("_valid_participant_count")
        .cast("long")
        .alias("valid_participant_count"),

        baseline_value.alias("baseline_g_co2e_per_km"),

        F.when(
            F.col("_global_eligibility_status")
            == ready_status,
            F.lit("global_average_of_personal_baseline"),
        )
        .otherwise(F.lit("insufficient_data"))
        .alias("method"),

        F.lit(baseline_policy_version)
        .alias("policy_version"),

        F.col("_global_eligibility_status")
        .alias("status"),

        baseline_value.alias("value"),

        F.col("eligible_participant_count")
        .cast("long")
        .alias("eligible_participant_count"),

        F.col("_eligibility_policy_version")
        .alias("eligibility_policy_version"),
    )