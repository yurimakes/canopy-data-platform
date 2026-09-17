import build_mission_response as mod


def assignment(aid, category, *, completed=False, affinity=True, difficulty=True, target=2):
    return {
        "assignment_id": aid,
        "category_id": category,
        "mission_template_id": f"template-{category}",
        "mission_family": f"family-{category}",
        "difficulty_band": "standard",
        "common_target_count": 2,
        "target_count": target,
        "affinity_comparable": affinity,
        "difficulty_comparable": difficulty,
        "preference_comparable": affinity,
        "completed": completed,
    }


def bundle():
    return {
        "bundle_id": "bundle-1",
        "campaign_id": "campaign-1",
        "user_id": "user-1",
        "week_start": "2026-09-14",
        "week_end": "2026-09-21",
        "policy_version": "mission-policy-v3.2",
        "common_target_count": 2,
        "missions": [
            assignment("a1", "challenge"),
            assignment("a2", "habit"),
            assignment("a3", "easy_win"),
            assignment("a4", "explore", affinity=False, difficulty=False, target=1),
        ],
    }


def progress(aid, count, rate, completed, trips):
    return {
        "assignment_id": aid,
        "progress_count": count,
        "achievement_rate": rate,
        "completed": completed,
        "qualified_trip_ids": trips,
    }


def test_emits_one_row_per_issued_assignment_and_keeps_incomplete():
    rows = mod.build_response_rows(
        [bundle()],
        [
            progress("a1", 2, 1.0, True, ["t1", "t2"]),
            progress("a2", 1, 0.5, False, ["t1"]),
        ],
    )
    assert len(rows) == 4
    by_id = {row["assignment_id"]: row for row in rows}
    assert by_id["a1"]["completed"] is True
    assert by_id["a1"]["mission_completed_count"] == 1
    assert by_id["a1"]["linked_trip_count"] == 2
    assert by_id["a2"]["completed"] is False
    assert by_id["a2"]["progress_count"] == 1
    assert by_id["a3"]["progress_count"] == 0
    assert by_id["a3"]["achievement_rate"] == 0.0
    assert by_id["a3"]["completed"] is False
    assert by_id["a4"]["affinity_comparable"] is False
    assert by_id["a4"]["difficulty_comparable"] is False


def test_learning_metadata_comes_from_bundle_not_progress():
    rows = mod.build_response_rows(
        [bundle()],
        [{
            "assignment_id": "a1",
            "progress_count": 2,
            "achievement_rate": 1.0,
            "completed": True,
            "qualified_trip_ids": ["t1", "t2"],
            "target_count": 999,
            "affinity_comparable": False,
        }],
    )
    row = {x["assignment_id"]: x for x in rows}["a1"]
    assert row["target_count"] == 2
    assert row["common_target_count"] == 2
    assert row["affinity_comparable"] is True
    assert row["preference_comparable"] is True
    assert row["policy_version"] == "mission-policy-v3.2"


def test_ui_events_are_optional_and_deduped_by_event_id():
    events = [
        {"event_id": "e1", "assignment_id": "a1", "event_type": "shown"},
        {"event_id": "e1", "assignment_id": "a1", "event_type": "shown"},
        {"event_id": "e2", "assignment_id": "a1", "event_type": "started"},
        {"event_id": "e3", "assignment_id": "a1", "event_type": "completed"},
    ]
    rows = mod.build_response_rows([bundle()], [], events)
    row = {x["assignment_id"]: x for x in rows}["a1"]
    assert row["mission_shown_count"] == 1
    assert row["mission_started_count"] == 1
    # UI completed must not create actual completion.
    assert row["mission_completed_count"] == 0
    assert row["completed"] is False


def test_linked_trip_count_uses_unique_progress_trip_ids():
    rows = mod.build_response_rows(
        [bundle()],
        [progress("a1", 2, 1.0, True, ["t1", "t1", "t2"])],
    )
    row = {x["assignment_id"]: x for x in rows}["a1"]
    assert row["linked_trip_count"] == 2


def test_unknown_progress_assignment_fails_closed():
    try:
        mod.build_response_rows(
            [bundle()],
            [progress("not-issued", 1, 1.0, True, ["t1"])],
        )
    except mod.MissionResponseError as exc:
        assert "not present in issued bundles" in str(exc)
    else:
        raise AssertionError("unknown progress assignment must fail closed")


def test_output_has_all_required_schema_fields():
    row = mod.build_response_rows([bundle()], [progress("a1", 2, 1.0, True, ["t1", "t2"])])[0]
    required = {
        "campaign_id", "user_id", "week_start", "week_end", "bundle_id", "assignment_id",
        "mission_template_id", "mission_family", "category_id", "difficulty_band",
        "common_target_count", "target_count", "affinity_comparable", "difficulty_comparable",
        "preference_comparable", "progress_count", "achievement_rate", "completed",
        "linked_trip_count", "policy_version", "response_version",
    }
    assert required <= set(row)
    assert row["response_version"] == "mission-response-v1"
