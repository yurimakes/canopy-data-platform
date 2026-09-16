"""Pure mission-policy logic shared by Functions, tests, and QA fixtures."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

ASSIGNMENT_NAMESPACE = uuid.UUID("fb93fab0-7786-49b3-aacb-748831d35a4e")


class MissionPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class MissionDecision:
    status: str
    template_id: str | None
    family: str | None
    title: str | None
    target_count: int | None
    selection_reason: str
    policy_version: str


def load_mission_policy(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        policy = yaml.safe_load(fh)
    if not isinstance(policy, dict) or not policy.get("policy_version"):
        raise MissionPolicyError("mission policy must contain policy_version")
    return policy


def policy_hash(policy: Mapping[str, Any]) -> str:
    canonical = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _number(profile: Mapping[str, Any], key: str) -> float | None:
    value = profile.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def choose_template(profile: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[str | None, str]:
    if profile.get("profile_status") != "ready":
        return None, "profile_not_ready"

    car_ratio = _number(profile, "car_ratio")
    if car_ratio is None:
        return None, "car_ratio_missing"

    selection = policy["selection"]
    car_threshold = float(selection["car_majority_threshold"])
    short_threshold = float(selection["short_car_majority_threshold"])

    if car_ratio > car_threshold:
        short_car_share = _number(profile, "short_car_share")
        if short_car_share is None:
            return None, "short_car_share_missing_for_car_majority"
        if short_car_share > short_threshold:
            return "short_car_to_active", "car_majority_and_short_car_majority"
        return "car_to_transit", "car_majority"

    # A user with zero car trips legitimately has short_car_share=null. That null must
    # not turn an otherwise valid low-carbon profile into collecting.
    return "low_carbon_maintain", "car_not_majority"


def _usable_previous_same_family(profile: Mapping[str, Any], family: str) -> bool:
    return (
        profile.get("previous_mission_family") == family
        and isinstance(profile.get("previous_target_count"), int)
        and profile.get("previous_target_count", 0) > 0
        and _number(profile, "previous_achievement_rate") is not None
    )


def compute_target_count(
    template_id: str,
    profile: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[int | None, str]:
    template = policy["templates"][template_id]
    strategy = template["target_strategy"]
    opportunity_raw = profile.get(template["opportunity_field"])
    if isinstance(opportunity_raw, bool) or not isinstance(opportunity_raw, int):
        return None, "opportunity_missing"
    opportunity = opportunity_raw
    if opportunity <= 0:
        return None, "no_observed_opportunity"

    if strategy == "maintain_observed":
        return opportunity, "maintain_observed_count"

    adaptive = policy["adaptive_target"]
    minimum = int(adaptive["minimum_target_count"])
    first = int(adaptive["first_target_count"])
    family = template["family"]

    if not _usable_previous_same_family(profile, family):
        return min(max(first, minimum), opportunity), "first_or_missing_same_family_result"

    previous_target = int(profile["previous_target_count"])
    rate = float(profile["previous_achievement_rate"])
    if rate >= 1.0:
        target = previous_target + int(adaptive["completed_increment"])
        reason = "same_family_completed_increment"
    elif rate <= 0.0:
        target = previous_target - int(adaptive["zero_achievement_decrement"])
        reason = "same_family_zero_decrement"
    else:
        target = previous_target
        reason = "same_family_partial_hold"

    target = max(minimum, target)
    target = min(target, opportunity)
    return target, reason


def decide_mission(profile: Mapping[str, Any], policy: Mapping[str, Any]) -> MissionDecision:
    template_id, selection_reason = choose_template(profile, policy)
    version = str(policy["policy_version"])
    if template_id is None:
        return MissionDecision(
            status="collecting",
            template_id=None,
            family=None,
            title=None,
            target_count=None,
            selection_reason=selection_reason,
            policy_version=version,
        )

    target_count, target_reason = compute_target_count(template_id, profile, policy)
    if target_count is None:
        return MissionDecision(
            status="collecting",
            template_id=None,
            family=None,
            title=None,
            target_count=None,
            selection_reason=f"{selection_reason}:{target_reason}",
            policy_version=version,
        )

    template = policy["templates"][template_id]
    return MissionDecision(
        status="assigned",
        template_id=template_id,
        family=str(template["family"]),
        title=str(template["title"]),
        target_count=target_count,
        selection_reason=f"{selection_reason}:{target_reason}",
        policy_version=version,
    )


def assignment_id(campaign_id: str, user_id: str, week_start: str) -> str:
    key = json.dumps([campaign_id, user_id, week_start], ensure_ascii=False, separators=(",", ":"))
    return "assign_" + str(uuid.uuid5(ASSIGNMENT_NAMESPACE, key))


def public_assignment(item: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    keys = (
        "assignment_id", "user_id", "campaign_id", "week_start", "week_end",
        "mission_template_id", "mission_family", "mission_name", "target_count",
        "status", "policy_version", "profile_source_week", "selection_reason",
    )
    return {key: item.get(key) for key in keys}


def assign_for_week(
    repo,
    policy: Mapping[str, Any],
    *,
    user_id: str,
    campaign_id: str,
    week_start: str,
    week_end: str,
    now_iso: str,
) -> dict[str, Any]:
    existing = repo.get_assignment(campaign_id, user_id, week_start)
    if existing:
        return {"status": "assigned", "assignment": public_assignment(existing), "idempotent": True}

    profile = repo.get_latest_profile(campaign_id, user_id)
    if not profile:
        return {"status": "collecting", "reason": "profile_missing", "week_start": week_start, "week_end": week_end}
    if profile.get("source_week_end") != week_start:
        return {
            "status": "collecting",
            "reason": "latest_profile_is_not_previous_completed_week",
            "week_start": week_start,
            "week_end": week_end,
        }

    decision = decide_mission(profile, policy)
    if decision.status != "assigned":
        return {
            "status": "collecting",
            "reason": decision.selection_reason,
            "week_start": week_start,
            "week_end": week_end,
        }

    aid = assignment_id(campaign_id, user_id, week_start)
    item = {
        "id": aid,
        "pk": repo.pk(campaign_id, user_id),
        "type": "mission_assignment",
        "assignment_id": aid,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "mission_template_id": decision.template_id,
        "mission_family": decision.family,
        "mission_name": decision.title,
        "target_count": decision.target_count,
        "progress_count": 0,
        "achievement_rate": 0.0,
        "completed": False,
        "status": "active",
        "policy_version": decision.policy_version,
        "policy_hash": policy_hash(policy),
        "profile_source_week": profile.get("source_week_start"),
        "profile_version": profile.get("profile_version"),
        "profile_hash": profile.get("profile_hash"),
        "selection_reason": decision.selection_reason,
        "created_at": now_iso,
    }
    saved = repo.create_assignment(item)
    return {"status": "assigned", "assignment": public_assignment(saved), "idempotent": False}


def get_for_week(repo, *, user_id: str, campaign_id: str, week_start: str, week_end: str) -> dict[str, Any]:
    item = repo.get_assignment(campaign_id, user_id, week_start)
    if not item:
        return {"status": "collecting", "reason": "assignment_not_issued", "week_start": week_start, "week_end": week_end}
    return {"status": "assigned", "assignment": public_assignment(item)}
