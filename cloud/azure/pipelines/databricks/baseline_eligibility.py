"""Eligibility only; the existing Personal/Global modules own the formulas."""
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
import json
import math
import os

import yaml


def load_eligibility_policy(path=None):
    # Git Folder OR the same directory tree extracted from the runtime bundle.
    path = Path(path or os.environ.get("CANOPY_BASELINE_ELIGIBILITY_PATH")
                or Path(__file__).resolve().parents[4] / "shared/configs/baseline_eligibility.yaml")
    if not path.is_file():
        raise FileNotFoundError(f"Eligibility YAML missing: {path}. Deploy the code/config bundle together.")
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    p, g = policy["personal"], policy["global"]
    for value in (p["minimum_observation_days"], p["minimum_confirmed_commute_trips"],
                  g["minimum_eligible_participants"]):
        if type(value) is not int or value <= 0:
            raise ValueError("Eligibility thresholds must be positive integers")
    if not isinstance(policy["policy_version"], str) or not policy["policy_version"]:
        raise ValueError("Eligibility policy_version required")
    if (p["status"] != {"before_eligible": "collecting", "when_eligible": "ready"}
            or g["status"] != {"below_minimum_participants": "collecting", "when_eligible": "ready"}
            or g["participant_rule"]["require_personal_status"] != p["status"]["when_eligible"]
            or p["cold_start"] != {"primary_baseline": "population", "personal_baseline_enabled": False}):
        raise ValueError("Unsupported eligibility statuses or cold-start policy")
    for key in ("require_positive_total_distance", "require_valid_total_carbon"):
        if type(p[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    return policy


def finite_nonnegative(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def evaluate_personal_eligibility(observation_days, trip_count, total_distance, total_carbon, policy):
    p = policy["personal"]
    reasons = []
    if not finite_nonnegative(observation_days) or observation_days < p["minimum_observation_days"]:
        reasons.append("observation_period_incomplete")
    if (not finite_nonnegative(trip_count) or int(trip_count) != trip_count
            or trip_count < p["minimum_confirmed_commute_trips"]):
        reasons.append("insufficient_confirmed_commute_trips")
    if p["require_positive_total_distance"] and (not finite_nonnegative(total_distance) or total_distance <= 0):
        reasons.append("invalid_total_distance")
    if p["require_valid_total_carbon"] and not finite_nonnegative(total_carbon):
        reasons.append("invalid_total_carbon")
    return {"status": p["status"]["before_eligible" if reasons else "when_eligible"],
            "policy_version": policy["policy_version"], "observation_days": observation_days,
            "confirmed_trip_count": trip_count, "reasons": reasons}


def evaluate_global_eligibility(eligible_participant_count, policy):
    g = policy["global"]
    if not finite_nonnegative(eligible_participant_count) or int(eligible_participant_count) != eligible_participant_count:
        raise ValueError("eligible_participant_count must be a non-negative integer")
    ready = eligible_participant_count >= g["minimum_eligible_participants"]
    return {"status": g["status"]["when_eligible" if ready else "below_minimum_participants"],
            "policy_version": policy["policy_version"],
            "eligible_participant_count": int(eligible_participant_count)}


def utc_instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("An ISO8601 timestamp with timezone is required")
    return value.astimezone(timezone.utc)


def observation_context(user_id, campaign_id, evaluated_at, identities):
    """Consume supplied existing records. Never infer signup from Trip timestamps."""
    members = [r for r in identities.get("memberships", [])
               if r.get("user_id") == user_id and r.get("campaign_id") == campaign_id]
    users = [r for r in identities.get("users", []) if r.get("user_id", r.get("id")) == user_id]
    if len(members) > 1 or len(users) > 1:
        return None, None, "ambiguous_identity"
    candidates = []
    if members:
        candidates.extend((f"membership.{k}", members[0].get(k))
                          for k in ("campaign_joined_at", "joined_at"))
    if users:
        candidates.extend((f"user.{k}", users[0].get(k)) for k in ("joined_at", "created_at"))
    for field, value in candidates:
        if value is None:
            continue
        try:
            age = utc_instant(evaluated_at) - utc_instant(value)
            if age.total_seconds() < 0:
                return None, field, "future_joined_at"
            return age.days, field, None
        except (TypeError, ValueError, OverflowError):
            return None, field, "invalid_joined_at"
    return None, None, "joined_at_missing"


def load_identities(path=None):
    # An integration input, not a new user DB or a generated membership date.
    path = path or os.environ.get("CANOPY_BASELINE_IDENTITIES_PATH")
    if not path:
        return {"users": [], "memberships": []}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(not isinstance(data.get(k, []), list) for k in ("users", "memberships")):
        raise ValueError("Identity input must contain users/memberships record lists")
    return data


def week_evaluation_time(week):
    year, number = week.split("-W")
    return datetime.fromisocalendar(int(year), int(number), 1).replace(tzinfo=timezone.utc)
