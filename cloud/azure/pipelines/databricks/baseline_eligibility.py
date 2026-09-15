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
    path = str(path or os.environ.get("CANOPY_BASELINE_ELIGIBILITY_PATH")
               or Path(__file__).resolve().parents[4] / "shared/configs/baseline_eligibility.yaml")
    if path.startswith("abfss://"):
        # Use the workspace's existing Storage access, never a key in the URI.
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        rows = spark.read.option("wholetext", True).text(path).limit(2).collect()
        if len(rows) != 1:
            raise ValueError("Eligibility Storage path must resolve to exactly one YAML file")
        content = rows[0]["value"]
    else:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Eligibility YAML missing: {path}. Deploy the code/config bundle together.")
        content = path.read_text(encoding="utf-8")
    policy = yaml.safe_load(content)
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


def load_identities(path=None, *, campaign_id=None, user_ids=(), client=None):
    """Read existing dates; never create/update a user or membership here."""
    path = path or os.environ.get("CANOPY_BASELINE_IDENTITIES_PATH")
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or any(not isinstance(data.get(k, []), list) for k in ("users", "memberships")):
            raise ValueError("Identity input must contain users/memberships record lists")
        if any(not isinstance(row, dict) for k in ("users", "memberships") for row in data.get(k, [])):
            raise ValueError("Identity entries must be records")
        if campaign_id is not None:
            wanted = set(user_ids)
            return {"users": [r for r in data.get("users", []) if r.get("user_id", r.get("id")) in wanted],
                    "memberships": [r for r in data.get("memberships", [])
                                    if r.get("user_id") in wanted and r.get("campaign_id") == campaign_id]}
        return data
    endpoint = os.environ.get("CANOPY_COSMOS_ENDPOINT") or os.environ.get("COSMOS_ENDPOINT")
    if client is None and not endpoint:
        return {"users": [], "memberships": []}
    database = os.environ.get("CANOPY_COSMOS_DATABASE")
    if not database or not campaign_id:
        raise ValueError("CANOPY_COSMOS_DATABASE and campaign_id required for identity lookup")
    from azure.cosmos import CosmosClient, exceptions
    from azure.identity import DefaultAzureCredential
    owns_client = client is None
    if owns_client:
        credential = os.environ.get("CANOPY_COSMOS_KEY") or DefaultAzureCredential()
        client = CosmosClient(endpoint, credential=credential)
    try:
        db = client.get_database_client(database)
        members = db.get_container_client(os.environ.get("CANOPY_MEMBERSHIPS_CONTAINER", "campaign_memberships"))
        users = db.get_container_client(os.environ.get("CANOPY_USERS_CONTAINER", "users"))
        result = {"users": [], "memberships": []}
        for uid in sorted(set(user_ids)):
            # Both containers use /user_id; all reads target one partition.
            for container, item_id, target, fields in (
                (members, campaign_id, "memberships", ("user_id", "campaign_id", "joined_at", "campaign_joined_at")),
                (users, uid, "users", ("id", "user_id", "created_at", "joined_at")),
            ):
                try:
                    item = container.read_item(item=item_id, partition_key=uid)
                except exceptions.CosmosResourceNotFoundError:
                    continue
                result[target].append({k: item[k] for k in fields if k in item})
        return result
    finally:
        if owns_client:
            client.close()
            if not isinstance(credential, str):
                credential.close()


def week_evaluation_time(week):
    year, number = week.split("-W")
    return datetime.fromisocalendar(int(year), int(number), 1).replace(tzinfo=timezone.utc)
