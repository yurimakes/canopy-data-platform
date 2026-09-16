import math
import yaml


def load_policy(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _finite_nonnegative(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def classify_reward_status(personal_baseline, global_baseline, population_baseline, actual):
    """Return status, selected baseline source/value, and machine-readable reason.

    Personal improvement keeps the teammate's original priority over Global maintenance.
    Population is a cold-start fallback only when Personal is not ready.
    """
    if not _finite_nonnegative(actual):
        return "not_eligible", None, None, "invalid_actual"

    if _finite_nonnegative(personal_baseline):
        personal = float(personal_baseline)
        actual = float(actual)
        if actual < personal:
            return "improved", "personal", personal, "actual_below_personal"

        if _finite_nonnegative(global_baseline) and actual <= float(global_baseline):
            return "maintained", "global", float(global_baseline), "actual_at_or_below_global"

        return "no_change", "personal", personal, "no_personal_improvement_or_global_maintenance"

    if _finite_nonnegative(population_baseline):
        return "population_fallback", "population", float(population_baseline), "personal_not_ready"

    return "not_eligible", None, None, "personal_not_ready_and_population_unavailable"


def compute_points(status, selected_baseline, actual, policy):
    if status == "not_eligible":
        return None, "not_eligible"

    if status == "no_change":
        return policy.get("points", {}).get("no_change", 0), "policy.points.no_change"

    conversion_rate = policy.get("point_formula", {}).get("conversion_rate")
    if conversion_rate is None:
        return None, "point_formula.conversion_rate_not_configured"
    if not _finite_nonnegative(conversion_rate) or float(conversion_rate) == 0:
        return None, "point_formula.invalid_conversion_rate"
    if not _finite_nonnegative(selected_baseline) or not _finite_nonnegative(actual):
        return None, "invalid_baseline_or_actual"

    delta = max(float(selected_baseline) - float(actual), 0.0)
    points = delta / float(conversion_rate)
    return points, f"max(delta={delta},0)/conversion_rate({conversion_rate})"


def is_payable(points):
    """Ledger must never persist a paid row with null/unconfigured points."""
    return _finite_nonnegative(points) and float(points) > 0


if __name__ == "__main__":
    scenarios = [
        ("Personal 개선", 150, 80, 120, 90, "improved"),
        ("Global 유지", 80, 100, 120, 80, "maintained"),
        ("첫 주 Population", None, 100, 120, 90, "population_fallback"),
        ("Population 없음", None, 100, None, 90, "not_eligible"),
        ("변화 없음", 80, 70, 120, 100, "no_change"),
    ]
    passed = True
    for name, personal, global_value, population, actual, expected in scenarios:
        result = classify_reward_status(personal, global_value, population, actual)[0]
        ok = result == expected
        passed = passed and ok
        print(f"{name}: 기대={expected} 실제={result} -> {'PASS' if ok else 'FAIL'}")
    print("전체 결과:", "PASS" if passed else "FAIL")
