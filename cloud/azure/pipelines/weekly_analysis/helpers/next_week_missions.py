"""Next Week Mission Bundle 생성 (mission-policy-v3.2 초안).

weekly_user_profile (PROFILE_SCHEMA) 각 행에서 다음 주 Mission Bundle
(MISSION_BUNDLE_SCHEMA 계약) 레코드를 만든다.

이 모듈은 ADLS, Cosmos, Lakeflow, ADF 쓰기를 포함하지 않는다. 순수 Python
계산 함수(build_bundle_for_profile 등)와 그 위의 얇은 Spark 변환
(build_next_week_missions)만 제공한다. 저장/발행은 파이프라인이 담당한다.

카탈로그(미션 family/템플릿 문구/완료 규칙)와 난이도 조정 폭은
DEFAULT_MISSION_POLICY에 초안으로 담았다. 카테고리 1개당 family 1개로
단순화했으며, 실제 문구·family 세분화·임계값은 정책 담당자 확정 전까지
이 초안을 사용한다 (팀 확인 필요).

profile_status가 "ready" / "active"가 아니면(collecting, history_only 등)
전체 발급을 cold-start starter로 취급한다: affinity_comparable=False,
difficulty_comparable=False. family_capability / category_preferences
이력이 개별적으로 없는 카테고리도 동일하게 이력 없음으로 처리한다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping

import pandas as pd

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

POLICY_VERSION = "mission-policy-v3.2"
CATEGORY_IDS = ("challenge", "habit", "easy_win", "explore")

try:
    CANONICAL_MISSION_POLICY_PATH = str(
        Path(__file__).resolve().parents[3] / "functions" / "func_canopy_dev" / "mission_policy.yaml"
    )
except IndexError: 
    CANONICAL_MISSION_POLICY_PATH = "cloud/azure/functions/func_canopy_dev/mission_policy.yaml"

DEFAULT_MISSION_POLICY: dict[str, Any] = {
    "policy_version": POLICY_VERSION,
    "default_common_target_count": 2,
    "min_target_count": 1,
    "max_target_count": 5,
    "cold_start_difficulty_band": "starter",
    "categories": {
        "challenge": {
            "category_label": "도전형",
            "mission_family": "car_to_transit",
            "mission_template_id": "tmpl-challenge-car-to-transit",
            "mission_name": "대중교통으로 출퇴근하기",
            "mission_description": "이번 주 대중교통(버스/철도)을 대표 이동수단으로 이용해보세요.",
            "progress_unit": "trip",
            "difficulty_band": "standard",
            "completion_rule": {
                "metric": "qualifying_trip_count",
                "accepted_primary_modes": ["bus", "rail"],
                "dedupe_key": "trip_id",
                "time_window": "assignment_week",
                "source": "canonical_ready_trip",
            },
        },
        "habit": {
            "category_label": "꾸준형",
            "mission_family": "low_carbon_habit",
            "mission_template_id": "tmpl-habit-low-carbon",
            "mission_name": "저탄소 이동 유지하기",
            "mission_description": "이번 주 저탄소 이동수단(도보/자전거/버스/철도)으로 이동한 날을 늘려보세요.",
            "progress_unit": "day",
            "difficulty_band": "standard",
            "completion_rule": {
                "metric": "distinct_day_count",
                "accepted_primary_modes": ["walk", "bike", "bus", "rail"],
                "dedupe_key": "trip_id",
                "time_window": "assignment_week",
                "source": "canonical_ready_trip",
            },
        },
        "easy_win": {
            "category_label": "쉬운 성공형",
            "mission_family": "short_car_to_active",
            "mission_template_id": "tmpl-easywin-short-car-to-active",
            "mission_name": "짧은 거리는 걷거나 자전거로",
            "mission_description": "2km 이내 짧은 이동을 도보나 자전거로 바꿔보세요.",
            "progress_unit": "trip",
            "difficulty_band": "easy",
            "completion_rule": {
                "metric": "qualifying_trip_count",
                "accepted_primary_modes": ["walk", "bike"],
                "max_trip_distance_km": 2.0,
                "dedupe_key": "trip_id",
                "time_window": "assignment_week",
                "source": "canonical_ready_trip",
            },
        },
        "explore": {
            "category_label": "탐험형",
            "mission_family": "mode_explorer",
            "mission_template_id": "tmpl-explore-mode-explorer",
            "mission_name": "새로운 이동수단 시도하기",
            "mission_description": "이번 주 평소와 다른 이동수단을 한 번 이상 시도해보세요.",
            "progress_unit": "mode",
            "difficulty_band": "easy",
            "completion_rule": {
                "metric": "distinct_mode_count",
                "accepted_primary_modes": ["walk", "bike", "bus", "rail"],
                "dedupe_key": "trip_id",
                "time_window": "assignment_week",
                "source": "canonical_ready_trip",
            },
        },
    },
}

REQUIRED_PROFILE_COLUMNS = (
    "user_id",
    "campaign_id",
    "effective_week_start",
    "source_week_start",
    "source_week_end",
    "profile_version",
    "profile_status",
    "profile_hash",
    "category_preferences_json",
    "difficulty_state_json",
    "family_capability_json",
)

OUTPUT_COLUMNS = (
    "id",
    "pk",
    "type",
    "bundle_id",
    "user_id",
    "campaign_id",
    "week_start",
    "week_end",
    "policy_version",
    "policy_hash",
    "profile_source_week",
    "profile_version",
    "profile_hash",
    "profile_status_at_issue",
    "common_target_count",
    "difficulty_reason",
    "created_at",
    "missions",
)


class MissionPolicyError(ValueError):
    """미션 정책 또는 profile 입력이 mission-policy-v3.2 계약을 위반할 때 발생."""


# ---------------------------------------------------------------------------
# 정책 검증
# ---------------------------------------------------------------------------

def load_mission_policy(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """기본 정책(DEFAULT_MISSION_POLICY)에 overrides를 얕은 병합해 검증한다.

    실제 정책 파일(YAML/Cosmos 등) 연결 전까지의 초안 로더다.
    """
    policy: dict[str, Any] = dict(DEFAULT_MISSION_POLICY)
    if overrides:
        policy.update(overrides)
    validate_mission_policy(policy)
    return policy


def validate_mission_policy(policy: Mapping[str, Any]) -> None:
    """정책 딕셔너리가 이 모듈이 요구하는 최소 계약을 만족하는지 확인한다."""
    if not isinstance(policy.get("policy_version"), str) or not policy["policy_version"]:
        raise MissionPolicyError("policy_version은 비어 있지 않은 문자열이어야 합니다")

    categories = policy.get("categories")
    if not isinstance(categories, Mapping) or not categories:
        raise MissionPolicyError("categories 카탈로그가 필요합니다")
    for category_id in CATEGORY_IDS:
        template = categories.get(category_id)
        if not isinstance(template, Mapping):
            raise MissionPolicyError(f"categories에 {category_id} 항목이 없습니다")
        for field in (
            "mission_family", "mission_template_id", "mission_name",
            "mission_description", "progress_unit", "difficulty_band",
            "completion_rule",
        ):
            if not template.get(field):
                raise MissionPolicyError(f"{category_id} 템플릿에 {field}가 없습니다")
        rule = template["completion_rule"]
        if not isinstance(rule, Mapping) or not rule.get("metric") or not rule.get("accepted_primary_modes"):
            raise MissionPolicyError(f"{category_id} completion_rule이 불완전합니다")

    for key in ("default_common_target_count", "min_target_count", "max_target_count"):
        value = policy.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise MissionPolicyError(f"{key}는 양의 정수여야 합니다")
    if policy["min_target_count"] > policy["max_target_count"]:
        raise MissionPolicyError("min_target_count는 max_target_count보다 클 수 없습니다")
    if not (policy["min_target_count"] <= policy["default_common_target_count"] <= policy["max_target_count"]):
        raise MissionPolicyError("default_common_target_count는 min/max_target_count 범위 안에 있어야 합니다")


def load_mission_policy_file(path: str | None = None) -> dict[str, Any]:
    """canonical mission_policy.yaml을 읽어 검증한 정책 dict를 반환한다.

    경로 우선순위: 인자 path > CANOPY_MISSION_POLICY_PATH 환경변수 >
    CANONICAL_MISSION_POLICY_PATH(cloud/azure/functions/func_canopy_dev/mission_policy.yaml,
    2026-09-17 최종 기준). abfss:// 경로는 Spark로, 그 외는 로컬 파일시스템으로 읽는다.

    파일이 아직 이 실행 환경에 배포되지 않았다면(개발/전환 구간) 경고만 남기고
    DEFAULT_MISSION_POLICY로 폴백한다 — 이 파이프라인의 다른 미배포 업스트림 입력
    처리 관례(_read_optional_delta의 PATH_NOT_FOUND 폴백)와 동일하다. YAML은
    있지만 내용이 계약을 어기면 조용히 넘어가지 않고 MissionPolicyError로
    fail closed한다.
    """
    resolved = str(path or os.environ.get("CANOPY_MISSION_POLICY_PATH") or CANONICAL_MISSION_POLICY_PATH)

    try:
        if resolved.startswith("abfss://"):
            from pyspark.sql import SparkSession  # 지연 임포트: Spark 미설치 환경 테스트 보호

            spark = SparkSession.builder.getOrCreate()
            rows = spark.read.option("wholetext", True).text(resolved).limit(2).collect()
            if len(rows) != 1:
                raise MissionPolicyError(
                    f"mission_policy.yaml Storage 경로는 파일 1개로 귀결돼야 합니다: {resolved}"
                )
            content = rows[0]["value"]
        else:
            file_path = Path(resolved)
            if not file_path.is_file():
                raise FileNotFoundError(resolved)
            content = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(
            f"[WARN] mission_policy.yaml 미배포({resolved}); "
            "개발용 DEFAULT_MISSION_POLICY로 대체합니다."
        )
        return load_mission_policy()

    import yaml  # 지연 임포트: 정책 파일을 실제로 읽을 때만 필요

    parsed = yaml.safe_load(content)
    if not isinstance(parsed, Mapping):
        raise MissionPolicyError(f"mission_policy.yaml 내용이 올바르지 않습니다: {resolved}")
    return load_mission_policy(parsed)


# ---------------------------------------------------------------------------
# profile 입력 검증 / 파싱
# ---------------------------------------------------------------------------

def _validate_profile_columns(columns: Iterable[str]) -> None:
    missing = [c for c in REQUIRED_PROFILE_COLUMNS if c not in set(columns)]
    if missing:
        raise MissionPolicyError(
            f"weekly_user_profile 입력에 필요한 컬럼이 없습니다: {missing}"
        )


def _safe_json_object(raw: Any) -> dict[str, Any]:

    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clip(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _resolve_target_count(
    family: str,
    family_capability: Mapping[str, Any],
    *,
    common_target_count: int,
    min_target_count: int,
    max_target_count: int,
) -> tuple[int, bool]:

    row = family_capability.get(family) if isinstance(family_capability, Mapping) else None
    if not isinstance(row, Mapping):
        return common_target_count, False

    last_target = row.get("last_target_count")
    if not isinstance(last_target, int) or isinstance(last_target, bool) or last_target <= 0:
        return common_target_count, False

    last_rate = row.get("last_achievement_rate")
    if not isinstance(last_rate, (int, float)) or isinstance(last_rate, bool):
        return _clip(last_target, min_target_count, max_target_count), True

    if last_rate >= 1.0:
        next_target = last_target + 1
    elif last_rate < 0.5:
        next_target = last_target - 1
    else:
        next_target = last_target
    return _clip(next_target, min_target_count, max_target_count), True


# ---------------------------------------------------------------------------
# 핵심 계산 (순수 Python, Spark 비의존 — 단위 테스트 대상)
# ---------------------------------------------------------------------------

def build_bundle_for_profile(
    profile: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:

    for field in (
        "user_id", "campaign_id", "effective_week_start",
        "profile_version", "profile_status",
    ):
        if not profile.get(field):
            raise MissionPolicyError(f"profile.{field}가 필요합니다")

    user_id = str(profile["user_id"])
    campaign_id = str(profile["campaign_id"])
    week_start = str(profile["effective_week_start"])
    week_end = str(profile.get("source_week_end") or week_start)
    profile_status = str(profile["profile_status"])

    is_cold_start = profile_status not in ("ready", "active")

    category_preferences = _safe_json_object(profile.get("category_preferences_json"))
    family_capability = _safe_json_object(profile.get("family_capability_json"))

    common_target_count = int(policy["default_common_target_count"])
    min_target_count = int(policy["min_target_count"])
    max_target_count = int(policy["max_target_count"])

    missions: list[dict[str, Any]] = []
    for category_id in CATEGORY_IDS:
        template = policy["categories"][category_id]
        family = str(template["mission_family"])

        target_count, has_capability_history = _resolve_target_count(
            family,
            family_capability,
            common_target_count=common_target_count,
            min_target_count=min_target_count,
            max_target_count=max_target_count,
        )

        preference_row = category_preferences.get(category_id)
        has_preference_history = isinstance(preference_row, Mapping) and bool(preference_row)

        affinity_comparable = (not is_cold_start) and has_preference_history
        difficulty_comparable = (not is_cold_start) and has_capability_history
        difficulty_band = (
            str(template["difficulty_band"])
            if difficulty_comparable
            else str(policy["cold_start_difficulty_band"])
        )

        completion_rule = dict(template["completion_rule"])
        completion_rule.setdefault("min_trip_distance_km", None)
        completion_rule.setdefault("max_trip_distance_km", None)
        completion_rule.setdefault("date_field", None)
        completion_rule["target_count"] = target_count

        missions.append({
            "assignment_id": f"{campaign_id}:{user_id}:{week_start}:{category_id}",
            "category_id": category_id,
            "category_label": template.get("category_label"),
            "mission_template_id": template["mission_template_id"],
            "mission_family": family,
            "mission_name": template["mission_name"],
            "mission_description": template["mission_description"],
            "progress_unit": template["progress_unit"],
            "difficulty_band": difficulty_band,
            "common_target_count": common_target_count,
            "target_count": target_count,
            "affinity_comparable": affinity_comparable,
            "difficulty_comparable": difficulty_comparable,
            "preference_comparable": affinity_comparable,
            "completion_rule": completion_rule,
            "progress_count": None,
            "achievement_rate": None,
            "completed": None,
            "status": None,
        })

    return {
        "id": f"mission-bundle:{campaign_id}:{user_id}:{week_start}",
        "pk": f"{campaign_id}:{user_id}",
        "type": "mission_bundle",
        "bundle_id": f"{campaign_id}:{user_id}:{week_start}",
        "user_id": user_id,
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "policy_version": str(policy["policy_version"]),
        "policy_hash": None,
        "profile_source_week": str(profile.get("source_week_start") or week_start),
        "profile_version": str(profile["profile_version"]),
        "profile_hash": profile.get("profile_hash"),
        "profile_status_at_issue": profile_status,
        "common_target_count": common_target_count,
        "difficulty_reason": "cold_start" if is_cold_start else "family_capability_history",
        "created_at": None,
        "missions": missions,
    }


# ---------------------------------------------------------------------------
# Spark 변환 (파이프라인이 호출하는 진입점)
# ---------------------------------------------------------------------------

def build_next_week_missions(
    profile_df: "DataFrame",
    schema: Any,
    policy: Mapping[str, Any] | None = None,
) -> "DataFrame":
    """weekly_user_profile(PROFILE_SCHEMA) → Mission Bundle(MISSION_BUNDLE_SCHEMA) 변환.

    `schema`는 파이프라인이 소유한 MISSION_BUNDLE_SCHEMA DDL 문자열(또는
    StructType)을 그대로 받는다. 이 헬퍼는 출력 계약 문자열을 복제하지 않고,
    호출부(weekly_pipeline.py)가 정의한 스키마를 신뢰한다.

    이 함수는 지연 평가되는 Spark 변환만 반환한다: collect/toPandas/write 등
    드라이버 액션이나 Cosmos/ADLS 호출을 포함하지 않는다.

    `policy`를 넘기지 않으면 canonical mission_policy.yaml
    (cloud/azure/functions/func_canopy_dev/mission_policy.yaml)을 읽는다.
    파일이 아직 없으면 DEFAULT_MISSION_POLICY로 폴백한다.
    """
    resolved_policy = (
        load_mission_policy(policy) if policy is not None else load_mission_policy_file()
    )
    _validate_profile_columns(profile_df.columns)

    def _map_partition(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
        for batch in batches:
            records = batch.to_dict("records")
            bundles = [
                build_bundle_for_profile(record, resolved_policy)
                for record in records
            ]
            if bundles:
                yield pd.DataFrame(bundles, columns=OUTPUT_COLUMNS)
            else:
                yield pd.DataFrame(columns=OUTPUT_COLUMNS)

    return profile_df.mapInPandas(_map_partition, schema=schema)
