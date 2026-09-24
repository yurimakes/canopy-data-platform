from cosmos_projection.projection import merge_projection


PAYLOAD = {
    "id": "trip-1",
    "trip_id": "trip-1",
    "user_id": "user-1",
    "processing_generation": 1,
    "finalization_hash": "hash-1",
    "status": "ready",
    "segments": [],
}


def test_missing_requires_explicit_sandbox_create():
    try:
        merge_projection(None, PAYLOAD, allow_missing_create=False)
    except ValueError as exc:
        assert "missing lifecycle Trip" in str(exc)
    else:
        raise AssertionError("expected missing lifecycle Trip failure")


def test_missing_sandbox_trip_can_be_created():
    action, body = merge_projection(None, PAYLOAD, allow_missing_create=True)
    assert action == "create"
    assert body["finalization_hash"] == "hash-1"
    assert body["cosmos_projected_at"]


def test_existing_lifecycle_fields_are_preserved():
    current = {
        "id": "trip-1",
        "user_id": "user-1",
        "processing_generation": 1,
        "status": "processing",
        "result_owner": "databricks",
        "trip_end_outbox": {"status": "published"},
        "created_at": "2026-01-01T00:00:00Z",
        "_etag": "etag",
    }
    action, body = merge_projection(current, PAYLOAD, allow_missing_create=False)
    assert action == "replace"
    assert body["status"] == "ready"
    assert body["trip_end_outbox"] == {"status": "published"}
    assert body["created_at"] == "2026-01-01T00:00:00Z"
    assert "_etag" not in body


def test_same_hash_is_idempotent():
    current = {**PAYLOAD, "_etag": "etag"}
    action, _ = merge_projection(current, PAYLOAD, allow_missing_create=False)
    assert action == "already_published"
