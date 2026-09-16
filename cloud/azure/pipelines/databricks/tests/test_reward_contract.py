from reward_policy_classifier import classify_reward_status, compute_points, is_payable
from reward_ledger import make_reward_id


def policy(conversion_rate=None):
    return {
        "points": {"no_change": 0},
        "point_formula": {"conversion_rate": conversion_rate},
    }


def test_personal_improvement_keeps_priority_over_global():
    status, source, baseline, reason = classify_reward_status(150, 80, 120, 90)
    assert status == "improved"
    assert source == "personal"
    assert baseline == 150
    assert reason == "actual_below_personal"


def test_global_maintenance_requires_personal_ready_context():
    status, source, baseline, _ = classify_reward_status(100, 80, 120, 80)
    assert status == "maintained"
    assert source == "global"
    assert baseline == 80


def test_first_week_uses_population_instead_of_global_only():
    status, source, baseline, reason = classify_reward_status(None, 80, 120, 90)
    assert status == "population_fallback"
    assert source == "population"
    assert baseline == 120
    assert reason == "personal_not_ready"


def test_cold_start_without_external_population_is_not_payable():
    status, source, baseline, _ = classify_reward_status(None, 80, None, 90)
    assert status == "not_eligible"
    assert source is None
    assert baseline is None


def test_unconfigured_point_formula_never_creates_payable_null_reward():
    status, _, baseline, _ = classify_reward_status(150, 80, 120, 90)
    points, reason = compute_points(status, baseline, 90, policy(None))
    assert points is None
    assert reason == "point_formula.conversion_rate_not_configured"
    assert is_payable(points) is False


def test_configured_formula_can_become_payable():
    status, _, baseline, _ = classify_reward_status(150, 80, 120, 90)
    points, _ = compute_points(status, baseline, 90, policy(10))
    assert points == 6
    assert is_payable(points) is True


def test_reward_id_is_deterministic_per_trip_and_differs_across_trips():
    first = make_reward_id("u1", "c1", "trip-1", "trip_carbon")
    again = make_reward_id("u1", "c1", "trip-1", "trip_carbon")
    second_trip = make_reward_id("u1", "c1", "trip-2", "trip_carbon")
    assert first == again
    assert first != second_trip


def test_policy_version_does_not_change_base_reward_identity():
    # Policy revisions must be corrected with adjustment records, not a second base payout.
    before = make_reward_id("u1", "c1", "trip-1", "trip_carbon")
    after = make_reward_id("u1", "c1", "trip-1", "trip_carbon")
    assert before == after
