"""주간 미션 정책 엔진.

사용자가 미션을 선택하지 않는다. 서버가 카테고리별 미션을 한 주에 함께 부여하고,
발급 시점의 완료 규칙까지 assignment에 스냅샷으로 고정한다.

중요:
- 이미 발급된 미션은 이후 policy 파일이 바뀌어도 판정 기준이 변하면 안 된다.
- category preference는 인과적 '선호' 추정치가 아니라 완료 이력 기반 affinity 신호다.
- affinity 비교 가능성과 다음 주 난이도 조정 가능성은 서로 다른 계약이다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

import yaml

BUNDLE_NAMESPACE = uuid.UUID("236139f2-dd02-4a85-b05b-3a62f7d3c6a4")
ASSIGNMENT_NAMESPACE = uuid.UUID("fb93fab0-7786-49b3-aacb-748831d35a4e")


class MissionPolicyError(ValueError):
    pass


def load_mission_policy(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        policy = yaml.safe_load(fh)
    if not isinstance(policy, dict) or not policy.get("policy_version"):
        raise MissionPolicyError("mission policy must contain policy_version")
    if not isinstance(policy.get("categories"), dict) or not isinstance(policy.get("catalog"), dict):
        raise MissionPolicyError("mission policy must contain categories and catalog")
    for template_id, template in policy["catalog"].items():
        if not isinstance(template, dict) or not isinstance(template.get("completion_rule"), dict):
            raise MissionPolicyError(f"template {template_id} must contain completion_rule")
        if not template["completion_rule"].get("metric"):
            raise MissionPolicyError(f"template {template_id} completion_rule.metric is required")
    return policy


def policy_hash(policy: Mapping[str, Any]) -> str:
    raw = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bundle_id(campaign_id: str, user_id: str, week_start: str) -> str:
    raw = json.dumps([campaign_id, user_id, week_start], ensure_ascii=False, separators=(",", ":"))
    return "bundle_" + str(uuid.uuid5(BUNDLE_NAMESPACE, raw))


def assignment_id(campaign_id: str, user_id: str, week_start: str, category_id: str) -> str:
    raw = json.dumps([campaign_id, user_id, week_start, category_id], ensure_ascii=False, separators=(",", ":"))
    return "assign_" + str(uuid.uuid5(ASSIGNMENT_NAMESPACE, raw))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _behavior_profile_is_current(profile: Mapping[str, Any] | None, week_start: str) -> bool:
    return bool(profile and profile.get("profile_status") == "ready" and profile.get("source_week_end") == week_start)


def _template_eligible(template: Mapping[str, Any], profile: Mapping[str, Any] | None, week_start: str) -> bool:
    if template.get("status", "active") != "active":
        return False
    if not _behavior_profile_is_current(profile, week_start):
        return bool(template.get("cold_start"))
    eligibility = template.get("eligibility")
    if not eligibility:
        return bool(template.get("cold_start"))
    value = _number((profile or {}).get(eligibility.get("field")))
    if value is None:
        return False
    if "gt" in eligibility and not value > float(eligibility["gt"]):
        return False
    if "gte" in eligibility and not value >= float(eligibility["gte"]):
        return False
    if "eq" in eligibility and not value == float(eligibility["eq"]):
        return False
    return True


def _pick_template_for_category(
    category_id: str,
    profile: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
    *,
    week_start: str,
) -> tuple[str, Mapping[str, Any]]:
    candidates = [
        (template_id, template)
        for template_id, template in policy["catalog"].items()
        if template.get("category_id") == category_id and template.get("status", "active") == "active"
    ]
    candidates.sort(key=lambda item: (int(item[1].get("priority", 9999)), item[0]))
    for template_id, template in candidates:
        if not template.get("cold_start") and _template_eligible(template, profile, week_start):
            return template_id, template
    for template_id, template in candidates:
        if template.get("cold_start"):
            return template_id, template
    raise MissionPolicyError(f"category {category_id} has no usable active template")


def common_target_count(profile: Mapping[str, Any] | None, policy: Mapping[str, Any]) -> tuple[int, str]:
    """다음 주 adaptive 미션에 적용할 공통 목표 숫자를 계산한다."""
    rule = policy["difficulty"]
    minimum = int(rule["minimum_target_count"])
    maximum = int(rule.get("maximum_target_count", 7))
    first = int(rule["first_target_count"])
    state = (profile or {}).get("difficulty_state") or {}
    previous_target = state.get("last_common_target_count")
    comparable = state.get("last_comparable_mission_count")
    completed = state.get("last_completed_comparable_count")
    if not isinstance(previous_target, int) or previous_target <= 0 or not isinstance(comparable, int) or comparable <= 0 or not isinstance(completed, int):
        return min(max(first, minimum), maximum), "first_or_missing_result"
    if completed >= comparable:
        target = previous_target + int(rule["completed_all_comparable_increment"])
        return min(max(minimum, target), maximum), "all_completed_increment"
    if completed <= 0:
        target = previous_target - int(rule["completed_none_comparable_decrement"])
        return min(max(minimum, target), maximum), "none_completed_decrement"
    return min(max(minimum, previous_target), maximum), "partial_completion_hold"


def _resolved_target(template: Mapping[str, Any], profile: Mapping[str, Any] | None, policy: Mapping[str, Any], common_target: int) -> int:
    minimum = int(policy["difficulty"]["minimum_target_count"])
    fixed = template.get("fixed_target_count")
    if isinstance(fixed, int) and not isinstance(fixed, bool) and fixed > 0:
        return max(minimum, fixed)

    target = common_target
    opportunity_field = template.get("opportunity_field")
    opportunity = (profile or {}).get(opportunity_field) if opportunity_field else None
    if (
        policy["difficulty"].get("opportunity_ceiling", True)
        and isinstance(opportunity, int)
        and not isinstance(opportunity, bool)
        and opportunity > 0
    ):
        target = min(target, opportunity)
    return max(minimum, int(target))


def _render(text: str | None, *, target_count: int) -> str | None:
    if not isinstance(text, str):
        return None
    return text.replace("{target_count}", str(target_count))


def _snapshot_completion_rule(template: Mapping[str, Any], *, target_count: int) -> dict[str, Any]:
    rule = copy.deepcopy(template["completion_rule"])
    rule["target_count"] = target_count
    rule.setdefault("dedupe_key", "trip_id")
    rule.setdefault("time_window", "assignment_week")
    rule.setdefault("source", "canonical_ready_trip")
    return rule


def build_bundle_missions(
    profile: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
    *,
    campaign_id: str,
    user_id: str,
    week_start: str,
) -> tuple[list[dict[str, Any]], int, str]:
    common_target, target_reason = common_target_count(profile, policy)
    categories = sorted(policy["categories"].items(), key=lambda item: (int(item[1].get("sort_order", 9999)), item[0]))
    missions: list[dict[str, Any]] = []
    for category_id, category in categories:
        template_id, template = _pick_template_for_category(category_id, profile, policy, week_start=week_start)
        target = _resolved_target(template, profile, policy, common_target)
        uses_fixed_target = isinstance(template.get("fixed_target_count"), int) and not isinstance(template.get("fixed_target_count"), bool)
        affinity_comparable = (
            target == common_target
            and template.get("difficulty_band", "standard") == "standard"
            and template.get("affinity_comparable", template.get("preference_comparable", True)) is True
        )
        difficulty_comparable = (
            not uses_fixed_target
            and target == common_target
            and template.get("difficulty_adaptive", True) is True
        )
        completion_rule = _snapshot_completion_rule(template, target_count=target)
        missions.append({
            "assignment_id": assignment_id(campaign_id, user_id, week_start, category_id),
            "category_id": category_id,
            "category_label": category["label"],
            "mission_template_id": template_id,
            "mission_family": template["family"],
            "mission_name": _render(template["title"], target_count=target),
            "mission_description": _render(template.get("description"), target_count=target),
            "progress_unit": template.get("progress_unit", "회"),
            "difficulty_band": template.get("difficulty_band", "standard"),
            "common_target_count": common_target,
            "target_count": target,
            "affinity_comparable": affinity_comparable,
            "difficulty_comparable": difficulty_comparable,
            "preference_comparable": affinity_comparable,
            "completion_rule": completion_rule,
            "progress_count": 0,
            "achievement_rate": 0.0,
            "completed": False,
            "status": "active",
        })
    return missions, common_target, target_reason


def public_bundle(item: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    keys = (
        "bundle_id", "user_id", "campaign_id", "week_start", "week_end", "policy_version", "policy_hash",
        "profile_status_at_issue", "common_target_count", "difficulty_reason", "missions",
    )
    return {key: item.get(key) for key in keys}


def issue_weekly_bundle(
    repo,
    policy: Mapping[str, Any],
    *,
    user_id: str,
    campaign_id: str,
    week_start: str,
    week_end: str,
    now_iso: str,
) -> dict[str, Any]:
    existing = repo.get_bundle(campaign_id, user_id, week_start)
    if existing:
        return {"status": "assigned", "bundle": public_bundle(existing), "idempotent": True}

    profile = repo.get_latest_profile(campaign_id, user_id)
    missions, common_target, reason = build_bundle_missions(
        profile,
        policy,
        campaign_id=campaign_id,
        user_id=user_id,
        week_start=week_start,
    )
    bid = bundle_id(campaign_id, user_id, week_start)
    item = {
        "id": bid,
        "pk": repo.pk(campaign_id, user_id),
        "type": "mission_bundle",
        "bundle_id": bid,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "policy_version": policy["policy_version"],
        "policy_hash": policy_hash(policy),
        "profile_source_week": (profile or {}).get("source_week_start"),
        "profile_version": (profile or {}).get("profile_version"),
        "profile_hash": (profile or {}).get("profile_hash"),
        "profile_status_at_issue": (
            "current" if _behavior_profile_is_current(profile, week_start)
            else "history_only" if profile else "cold_start"
        ),
        "common_target_count": common_target,
        "difficulty_reason": reason,
        "missions": missions,
        "created_at": now_iso,
    }
    saved = repo.create_bundle(item)
    return {"status": "assigned", "bundle": public_bundle(saved), "idempotent": False}


def get_week_state(
    repo,
    policy: Mapping[str, Any],
    *,
    user_id: str,
    campaign_id: str,
    week_start: str,
    week_end: str,
    now_iso: str,
) -> dict[str, Any]:
    return issue_weekly_bundle(
        repo,
        policy,
        user_id=user_id,
        campaign_id=campaign_id,
        week_start=week_start,
        week_end=week_end,
        now_iso=now_iso,
    )