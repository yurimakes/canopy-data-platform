from copy import deepcopy

import mission_progress as mod


CAMPAIGN = "mission-progress-test"
USER = "user-001"
WEEK_START = "2026-09-14"
WEEK_END = "2026-09-21"
TZ = "Asia/Seoul"
AS_OF_ACTIVE = "2026-09-17T03:00:00Z"
AS_OF_EXPIRED = "2026-09-21T15:00:00Z"


def assignment(
    assignment_id,
    category_id,
    metric,
    modes,
    *,
    target=1,
    min_km=None,
    max_km=None,
):
    rule = {
        "metric": metric,
        "accepted_primary_modes": list(modes),
        "target_count": target,
        "dedupe_key": "trip_id",
        "time_window": "assignment_week",
        "source": "canonical_ready_trip",
    }
    if min_km is not None:
        rule["min_trip_distance_km"] = min_km
    if max_km is not None:
        rule["max_trip_distance_km"] = max_km
    return {
        "assignment_id": assignment_id,
        "category_id": category_id,
        "mission_template_id": f"template-{category_id}",
        "mission_family": f"family-{category_id}",
        "target_count": target,
        "completion_rule": rule,
    }


def bundle(*missions):
    return {
        "bundle_id": "bundle-test-001",
        "campaign_id": CAMPAIGN,
        "user_id": USER,
        "week_start": WEEK_START,
        "week_end": WEEK_END,
        "policy_version": "mission-policy-v3.2",
        "missions": list(missions),
    }


def trip(
    trip_id,
    ended_at,
    *segments,
    status="ready",
    updated_at=None,
    generation=1,
    user_id=USER,
    campaign_id=CAMPAIGN,
):
    return {
        "trip_id": trip_id,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "status": status,
        "ended_at": ended_at,
        "updated_at": updated_at or ended_at,
        "processing_generation": generation,
        "finalization_hash": f"hash-{trip_id}-{generation}",
        "segments": [
            {"model_prediction": mode, "distance_m": distance}
            for mode, distance in segments
        ],
    }


def evaluate(one_assignment, trips, *, as_of=AS_OF_ACTIVE):
    b = bundle(one_assignment)
    return mod.evaluate_assignment_progress(
        bundle=b,
        assignment=one_assignment,
        trips=trips,
        campaign_timezone=TZ,
        as_of_iso=as_of,
    )


def test_qualifying_trip_count_respects_primary_mode_and_min_distance():
    a = assignment(
        "assign-challenge",
        "challenge",
        "qualifying_trip_count",
        ["bus", "rail"],
        target=2,
        min_km=3.0,
    )
    trips = [
        trip("t1", "2026-09-14T00:00:00Z", ("bus", 3500)),
        trip("t2", "2026-09-15T00:00:00Z", ("rail", 4000)),
        trip("t3", "2026-09-16T00:00:00Z", ("bus", 2500)),
        trip("t4", "2026-09-17T00:00:00Z", ("car", 5000)),
    ]

    result = evaluate(a, trips)

    assert result["progress_count"] == 2
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert result["achievement_rate"] == 1.0
    assert result["qualified_trip_ids"] == ["t1", "t2"]
    assert result["completed_at"] == "2026-09-15T00:00:00+00:00"


def test_distinct_day_count_uses_campaign_local_date_not_utc_date():
    a = assignment(
        "assign-habit",
        "habit",
        "distinct_day_count",
        ["bus", "rail"],
        target=2,
    )
    trips = [
        # 2026-09-14 23:30 KST
        trip("t1", "2026-09-14T14:30:00Z", ("bus", 1000)),
        # 2026-09-15 00:30 KST, only one hour later but a different local date
        trip("t2", "2026-09-14T15:30:00Z", ("bus", 1000)),
        # Same local date as t2; must not increment distinct_day_count
        trip("t3", "2026-09-15T02:00:00Z", ("rail", 1000)),
    ]

    result = evaluate(a, trips)

    assert result["progress_count"] == 2
    assert result["completed"] is True
    assert result["qualified_local_dates"] == ["2026-09-14", "2026-09-15"]
    assert result["completed_at"] == "2026-09-14T15:30:00+00:00"


def test_distinct_mode_count_counts_unique_accepted_primary_modes():
    a = assignment(
        "assign-explore",
        "explore",
        "distinct_mode_count",
        ["walk", "bike"],
        target=2,
    )
    trips = [
        trip("t1", "2026-09-14T00:00:00Z", ("walk", 800)),
        trip("t2", "2026-09-15T00:00:00Z", ("walk", 1200)),
        trip("t3", "2026-09-16T00:00:00Z", ("bike", 1500)),
    ]

    result = evaluate(a, trips)

    assert result["progress_count"] == 2
    assert result["qualified_primary_modes"] == ["bike", "walk"]
    assert result["completed"] is True
    assert result["completed_at"] == "2026-09-16T00:00:00+00:00"


def test_primary_mode_tie_and_invalid_segment_are_excluded_not_arbitrated():
    a = assignment(
        "assign-easy",
        "easy_win",
        "qualifying_trip_count",
        ["walk", "bike"],
        target=1,
        max_km=2.0,
    )
    trips = [
        trip("tie", "2026-09-14T00:00:00Z", ("walk", 500), ("bike", 500)),
        trip("invalid", "2026-09-15T00:00:00Z", ("walk", 500), (None, 300)),
    ]

    result = evaluate(a, trips)

    assert result["progress_count"] == 0
    assert result["completed"] is False
    assert result["qualified_trip_ids"] == []
    assert result["primary_mode_invalid_reasons"] == {
        "primary_mode_tie": 1,
        "invalid_segment": 1,
    }


def test_latest_trip_version_replaces_older_contribution_before_ready_filter():
    a = assignment(
        "assign-challenge",
        "challenge",
        "qualifying_trip_count",
        ["bus"],
        target=1,
    )
    trips = [
        trip(
            "same-trip",
            "2026-09-14T00:00:00Z",
            ("bus", 3500),
            updated_at="2026-09-14T01:00:00Z",
            generation=1,
        ),
        # A later correction invalidates the old ready result.
        trip(
            "same-trip",
            "2026-09-14T00:00:00Z",
            ("bus", 3500),
            status="superseded",
            updated_at="2026-09-14T02:00:00Z",
            generation=2,
        ),
    ]

    result = evaluate(a, trips)

    assert result["progress_count"] == 0
    assert result["qualified_trip_ids"] == []
    assert result["completed"] is False


def test_same_trip_id_is_counted_once_and_recompute_is_idempotent():
    a = assignment(
        "assign-challenge",
        "challenge",
        "qualifying_trip_count",
        ["bus"],
        target=2,
    )
    duplicated = trip("t1", "2026-09-14T00:00:00Z", ("bus", 3500))
    trips = [duplicated, deepcopy(duplicated), trip("t2", "2026-09-15T00:00:00Z", ("bus", 3500))]

    first = evaluate(a, trips)
    second = evaluate(a, list(reversed(trips)))

    assert first["progress_count"] == 2
    assert first["qualified_trip_ids"] == ["t1", "t2"]
    comparable_first = {k: v for k, v in first.items() if k != "updated_at"}
    comparable_second = {k: v for k, v in second.items() if k != "updated_at"}
    assert comparable_first == comparable_second


def test_trip_outside_assignment_week_does_not_progress_mission():
    a = assignment(
        "assign-challenge",
        "challenge",
        "qualifying_trip_count",
        ["bus"],
        target=1,
    )
    trips = [
        # Before Monday 00:00 KST = 2026-09-13 15:00Z
        trip("before", "2026-09-13T14:59:59Z", ("bus", 5000)),
        # Exactly next Monday 00:00 KST; exclusive end boundary
        trip("after", "2026-09-20T15:00:00Z", ("bus", 5000)),
    ]

    result = evaluate(a, trips)

    assert result["progress_count"] == 0
    assert result["qualified_trip_ids"] == []


def test_incomplete_assignment_becomes_expired_after_week_end():
    a = assignment(
        "assign-challenge",
        "challenge",
        "qualifying_trip_count",
        ["bus"],
        target=2,
    )
    trips = [trip("t1", "2026-09-14T00:00:00Z", ("bus", 3500))]

    result = evaluate(a, trips, as_of=AS_OF_EXPIRED)

    assert result["progress_count"] == 1
    assert result["achievement_rate"] == 0.5
    assert result["completed"] is False
    assert result["status"] == "expired"


def test_one_trip_may_progress_multiple_assignments_but_once_per_assignment():
    challenge = assignment(
        "assign-challenge",
        "challenge",
        "qualifying_trip_count",
        ["walk", "bike", "bus", "rail"],
        target=1,
        min_km=2.0,
    )
    habit = assignment(
        "assign-habit",
        "habit",
        "distinct_day_count",
        ["walk", "bike", "bus", "rail"],
        target=1,
    )
    explore = assignment(
        "assign-explore",
        "explore",
        "distinct_mode_count",
        ["walk", "bike", "bus", "rail"],
        target=1,
    )
    b = bundle(challenge, habit, explore)
    trips = [trip("shared", "2026-09-14T00:00:00Z", ("walk", 2500))]

    rows = mod.evaluate_bundle_progress(
        bundle=b,
        trips=trips,
        campaign_timezone=TZ,
        as_of_iso=AS_OF_ACTIVE,
    )

    assert len(rows) == 3
    assert {row["assignment_id"]: row["progress_count"] for row in rows} == {
        "assign-challenge": 1,
        "assign-habit": 1,
        "assign-explore": 1,
    }
    assert all(row["qualified_trip_ids"] == ["shared"] for row in rows)


def test_frozen_completion_rule_snapshot_controls_progress():
    a = assignment(
        "assign-frozen",
        "challenge",
        "qualifying_trip_count",
        ["bus"],
        target=1,
        min_km=3.0,
    )
    # There is intentionally no current mission-policy input to the evaluator.
    # The issued snapshot alone decides that 2.5 km does not qualify.
    result = evaluate(
        a,
        [trip("t1", "2026-09-14T00:00:00Z", ("bus", 2500))],
    )

    assert result["progress_count"] == 0
    assert result["completed"] is False


def test_invalid_completion_rule_fails_closed():
    a = assignment(
        "assign-bad",
        "challenge",
        "qualifying_trip_count",
        ["bus"],
        target=1,
    )
    a["completion_rule"]["source"] = "current_policy"

    try:
        evaluate(a, [])
    except mod.MissionProgressError as exc:
        assert "canonical_ready_trip" in str(exc)
    else:
        raise AssertionError("invalid completion_rule source must fail closed")
