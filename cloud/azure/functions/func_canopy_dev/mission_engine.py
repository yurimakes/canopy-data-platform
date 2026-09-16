"""Pure weekly-mission recommendation, offer, and selection policy logic."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

import yaml

ASSIGNMENT_NAMESPACE = uuid.UUID("fb93fab0-7786-49b3-aacb-748831d35a4e")
OFFER_NAMESPACE = uuid.UUID("236139f2-dd02-4a85-b05b-3a62f7d3c6a4")


class MissionPolicyError(ValueError):
    pass


class MissionSelectionError(ValueError):
    pass


def load_mission_policy(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        policy = yaml.safe_load(fh)
    if not isinstance(policy, dict) or not policy.get("policy_version"):
        raise MissionPolicyError("mission policy must contain policy_version")
    if not isinstance(policy.get("categories"), dict) or not isinstance(policy.get("catalog"), dict):
        raise MissionPolicyError("mission policy must contain categories and catalog")
    return policy


def policy_hash(policy: Mapping[str, Any]) -> str:
    canonical = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assignment_id(campaign_id: str, user_id: str, week_start: str) -> str:
    raw = json.dumps([campaign_id, user_id, week_start], ensure_ascii=False, separators=(",", ":"))
    return "assign_" + str(uuid.uuid5(ASSIGNMENT_NAMESPACE, raw))


def offer_set_id(campaign_id: str, user_id: str, week_start: str) -> str:
    raw = json.dumps([campaign_id, user_id, week_start], ensure_ascii=False, separators=(",", ":"))
    return "offer_" + str(uuid.uuid5(OFFER_NAMESPACE, raw))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _behavior_profile_is_current(profile: Mapping[str, Any] | None, week_start: str) -> bool:
    return bool(
        profile
        and profile.get("profile_status") == "ready"
        and profile.get("source_week_end") == week_start
    )


def category_preference_score(
    profile: Mapping[str, Any] | None,
    category_id: str,
    policy: Mapping[str, Any],
) -> tuple[float, int]:
    learning = policy["preference_learning"]
    prior_alpha = float(learning["prior_alpha"])
    prior_beta = float(learning["prior_beta"])
    pref = (profile or {}).get("category_preferences") or {}
    state = pref.get(category_id) or {}
    alpha = _number(state.get("alpha"))
    beta = _number(state.get("beta"))
    alpha = prior_alpha if alpha is None else alpha
    beta = prior_beta if beta is None else beta
    denominator = alpha + beta
    score = alpha / denominator if denominator > 0 else 0.5
    observations = max(0, int(round(alpha + beta - prior_alpha - prior_beta)))
    return score, observations


def _template_eligible(template: Mapping[str, Any], profile: Mapping[str, Any] | None, week_start: str) -> bool:
    if not _behavior_profile_is_current(profile, week_start):
        return bool(template.get("cold_start"))

    eligibility = template.get("eligibility")
    if not eligibility:
        return bool(template.get("cold_start"))
    field = eligibility.get("field")
    value = _number((profile or {}).get(field))
    if value is None:
        return False
    if "gt" in eligibility and not value > float(eligibility["gt"]):
        return False
    if "gte" in eligibility and not value >= float(eligibility["gte"]):
        return False
    return True


def _family_state(profile: Mapping[str, Any] | None, family: str) -> Mapping[str, Any]:
    return (((profile or {}).get("family_capability") or {}).get(family) or {})


def compute_target_count(
    template: Mapping[str, Any],
    profile: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
    *,
    week_start: str,
) -> tuple[int, str]:
    adaptive = policy["adaptive_target"]
    minimum = int(adaptive["minimum_target_count"])
    first = int(adaptive["first_target_count"])
    strategy = template["target_strategy"]

    if strategy in {"starter_minimum", "minimum_one"}:
        return minimum, strategy

    field = template.get("opportunity_field")
    opportunity = (profile or {}).get(field) if field else None
    if isinstance(opportunity, bool) or not isinstance(opportunity, int) or opportunity <= 0:
        return minimum, "opportunity_unavailable_minimum"

    if strategy == "maintain_observed":
        return max(minimum, opportunity), "maintain_observed"

    if strategy != "adaptive_family":
        raise MissionPolicyError(f"unsupported target strategy: {strategy}")

    family = str(template["family"])
    state = _family_state(profile, family)
    previous_target = state.get("last_target_count")
    rate = _number(state.get("last_achievement_rate"))
    if not isinstance(previous_target, int) or previous_target <= 0 or rate is None:
        target = first
        reason = "family_first_or_missing_result"
    elif rate >= 1.0:
        target = previous_target + int(adaptive["completed_increment"])
        reason = "family_completed_increment"
    elif rate <= 0.0:
        target = previous_target - int(adaptive["zero_achievement_decrement"])
        reason = "family_zero_decrement"
    else:
        target = previous_target
        reason = "family_partial_hold"

    target = max(minimum, target)
    if adaptive.get("opportunity_ceiling", True):
        target = min(target, opportunity)
    return target, reason


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
        if template.get("category_id") == category_id
    ]
    candidates.sort(key=lambda item: (int(item[1].get("priority", 9999)), item[0]))

    for template_id, template in candidates:
        if not template.get("cold_start") and _template_eligible(template, profile, week_start):
            return template_id, template
    for template_id, template in candidates:
        if template.get("cold_start"):
            return template_id, template
    raise MissionPolicyError(f"category {category_id} has no usable template")


def build_offer_candidates(
    profile: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
    *,
    week_start: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    categories = sorted(
        policy["categories"].items(),
        key=lambda item: (int(item[1].get("sort_order", 9999)), item[0]),
    )
    for category_id, category in categories:
        template_id, template = _pick_template_for_category(
            category_id, profile, policy, week_start=week_start
        )
        target, target_reason = compute_target_count(
            template, profile, policy, week_start=week_start
        )
        score, observations = category_preference_score(profile, category_id, policy)
        result.append({
            "category_id": category_id,
            "category_label": category["label"],
            "mission_template_id": template_id,
            "mission_family": template["family"],
            "mission_name": template["title"],
            "target_count": target,
            "preference_score": round(score, 6),
            "preference_observations": observations,
            "fit_reason": target_reason,
            "is_recommended": False,
        })

    result.sort(
        key=lambda item: (
            -item["preference_score"],
            int(policy["categories"][item["category_id"]].get("sort_order", 9999)),
            item["mission_template_id"],
        )
    )
    if result:
        result[0]["is_recommended"] = True
    return result


def public_assignment(item: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    keys = (
        "assignment_id", "offer_set_id", "user_id", "campaign_id", "week_start", "week_end",
        "category_id", "category_label", "mission_template_id", "mission_family", "mission_name",
        "target_count", "status", "policy_version", "profile_source_week", "selection_reason",
    )
    return {key: item.get(key) for key in keys}


def public_offer_set(item: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "offer_set_id": item.get("offer_set_id"),
        "user_id": item.get("user_id"),
        "campaign_id": item.get("campaign_id"),
        "week_start": item.get("week_start"),
        "week_end": item.get("week_end"),
        "policy_version": item.get("policy_version"),
        "profile_status_at_offer": item.get("profile_status_at_offer"),
        "candidates": item.get("candidates") or [],
        "selected_mission_template_id": item.get("selected_mission_template_id"),
    }


def issue_offer_set(
    repo,
    policy: Mapping[str, Any],
    *,
    user_id: str,
    campaign_id: str,
    week_start: str,
    week_end: str,
    now_iso: str,
) -> dict[str, Any]:
    existing_assignment = repo.get_assignment(campaign_id, user_id, week_start)
    if existing_assignment:
        return {"status": "assigned", "assignment": public_assignment(existing_assignment)}

    existing = repo.get_offer_set(campaign_id, user_id, week_start)
    if existing:
        return {"status": "awaiting_selection", "offer_set": public_offer_set(existing), "idempotent": True}

    profile = repo.get_latest_profile(campaign_id, user_id)
    profile_for_behavior = profile if _behavior_profile_is_current(profile, week_start) else profile
    candidates = build_offer_candidates(profile_for_behavior, policy, week_start=week_start)
    oid = offer_set_id(campaign_id, user_id, week_start)
    item = {
        "id": oid,
        "pk": repo.pk(campaign_id, user_id),
        "type": "mission_offer_set",
        "offer_set_id": oid,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "policy_version": policy["policy_version"],
        "policy_hash": policy_hash(policy),
        "profile_source_week": (profile or {}).get("source_week_start"),
        "profile_version": (profile or {}).get("profile_version"),
        "profile_hash": (profile or {}).get("profile_hash"),
        "profile_status_at_offer": (
            "current" if _behavior_profile_is_current(profile, week_start)
            else "preference_only" if profile else "cold_start"
        ),
        "candidates": candidates,
        "selected_mission_template_id": None,
        "created_at": now_iso,
    }
    saved = repo.create_offer_set(item)
    return {"status": "awaiting_selection", "offer_set": public_offer_set(saved), "idempotent": False}


def select_mission(
    repo,
    policy: Mapping[str, Any],
    *,
    user_id: str,
    campaign_id: str,
    week_start: str,
    week_end: str,
    requested_offer_set_id: str,
    mission_template_id: str,
    now_iso: str,
) -> dict[str, Any]:
    existing = repo.get_assignment(campaign_id, user_id, week_start)
    if existing:
        if existing.get("mission_template_id") != mission_template_id:
            return {
                "status": "assigned",
                "assignment": public_assignment(existing),
                "idempotent": True,
                "selection_conflict": True,
            }
        return {"status": "assigned", "assignment": public_assignment(existing), "idempotent": True}

    offer = repo.get_offer_set(campaign_id, user_id, week_start)
    if not offer or offer.get("offer_set_id") != requested_offer_set_id:
        raise MissionSelectionError("offer_set_not_found")

    selected = next(
        (c for c in offer.get("candidates", []) if c.get("mission_template_id") == mission_template_id),
        None,
    )
    if not selected:
        raise MissionSelectionError("mission_not_in_offer_set")

    aid = assignment_id(campaign_id, user_id, week_start)
    item = {
        "id": aid,
        "pk": repo.pk(campaign_id, user_id),
        "type": "mission_assignment",
        "assignment_id": aid,
        "offer_set_id": offer["offer_set_id"],
        "user_id": user_id,
        "campaign_id": campaign_id,
        "week_start": week_start,
        "week_end": week_end,
        "category_id": selected["category_id"],
        "category_label": selected["category_label"],
        "mission_template_id": selected["mission_template_id"],
        "mission_family": selected["mission_family"],
        "mission_name": selected["mission_name"],
        "target_count": int(selected["target_count"]),
        "progress_count": 0,
        "achievement_rate": 0.0,
        "completed": False,
        "status": "active",
        "policy_version": offer["policy_version"],
        "policy_hash": offer.get("policy_hash"),
        "profile_source_week": offer.get("profile_source_week"),
        "profile_version": offer.get("profile_version"),
        "profile_hash": offer.get("profile_hash"),
        "selection_reason": "user_selected_from_offer_set",
        "selected_at": now_iso,
        "created_at": now_iso,
    }
    saved = repo.create_assignment(item)
    repo.mark_offer_selected(offer, selected["mission_template_id"], now_iso)
    return {"status": "assigned", "assignment": public_assignment(saved), "idempotent": False}


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
    assignment = repo.get_assignment(campaign_id, user_id, week_start)
    if assignment:
        return {"status": "assigned", "assignment": public_assignment(assignment)}
    return issue_offer_set(
        repo,
        policy,
        user_id=user_id,
        campaign_id=campaign_id,
        week_start=week_start,
        week_end=week_end,
        now_iso=now_iso,
    )
