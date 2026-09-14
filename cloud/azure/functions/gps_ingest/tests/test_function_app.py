import json

import azure.functions as func
import pytest

from function_app import CORE_FIELDS, _extract_core_fields, gps_ingest


class FakeEventHubOutput:
    def __init__(self) -> None:
        self.value: str | None = None

    def set(self, value: str) -> None:
        self.value = value


def synthetic_event() -> dict[str, object]:
    return {
        "event_id": "evt_unit_0001",
        "user_id": "user_unit_01",
        "trip_id": "trip_unit_001",
        "event_time": "2026-09-11T00:00:01.123Z",
        "lat": 12.345678,
        "lon": -45.678901,
        "accuracy": 8.5,
        "speed": 1.25,
        "sequence": 1,
        "schema_version": "canopy.gps.collector.v0.1",
    }


def invoke_body(body: bytes) -> tuple[func.HttpResponse, FakeEventHubOutput]:
    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/gps",
        headers={"content-type": "application/json"},
        params={},
        route_params={},
        body=body,
    )
    output = FakeEventHubOutput()
    response = gps_ingest(request, output)
    return response, output


def invoke(payload: object) -> tuple[func.HttpResponse, FakeEventHubOutput]:
    return invoke_body(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def response_json(response: func.HttpResponse) -> dict[str, object]:
    return json.loads(response.get_body())


def test_normal_synthetic_event_returns_202_and_sets_output() -> None:
    payload = synthetic_event()
    response, output = invoke(payload)

    assert response.status_code == 202
    assert response_json(response) == {"status": "accepted"}
    assert output.value is not None
    assert isinstance(output.value, str)
    assert json.loads(output.value) == payload


def test_null_speed_is_accepted_and_preserved() -> None:
    payload = synthetic_event()
    payload["speed"] = None

    response, output = invoke(payload)

    assert response.status_code == 202
    assert json.loads(output.value)["speed"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("lat", 91),
        ("lon", 181),
        ("speed", "not-a-number"),
        ("sequence", True),
    ),
)
def test_values_rejected_by_old_validation_are_accepted(
    field: str, value: object
) -> None:
    payload = synthetic_event()
    payload[field] = value

    response, output = invoke(payload)

    assert response.status_code == 202
    assert json.loads(output.value) == payload


def test_missing_previously_required_keys_are_accepted() -> None:
    payload = synthetic_event()
    del payload["accuracy"]
    del payload["speed"]

    response, output = invoke(payload)

    assert response.status_code == 202
    assert json.loads(output.value) == payload


def test_extra_and_unknown_fields_are_preserved() -> None:
    payload = synthetic_event()
    payload["device_id"] = "device_unit_01"
    payload["raw_location"] = {
        "synthetic": True,
        "provider_extension": [1, None, {"quality": "unverified"}],
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    response, output = invoke_body(body)

    assert response.status_code == 202
    assert output.value == body.decode("utf-8")
    assert json.loads(output.value) == payload


def test_core_fields_are_extracted_without_extra_fields() -> None:
    payload = synthetic_event()
    payload["provider_extension"] = {"quality": "unverified"}

    core_fields = _extract_core_fields(payload)

    assert tuple(core_fields) == CORE_FIELDS
    assert core_fields == {field: payload[field] for field in CORE_FIELDS}
    assert "provider_extension" not in core_fields


def test_missing_core_fields_are_extracted_as_none_without_rejection() -> None:
    payload = {"event_id": "evt_partial", "provider_extension": True}

    response, output = invoke(payload)
    core_fields = _extract_core_fields(payload)

    assert response.status_code == 202
    assert core_fields["event_id"] == "evt_partial"
    assert core_fields["speed"] is None
    assert set(core_fields) == set(CORE_FIELDS)
    assert json.loads(output.value) == payload
    assert json.loads(output.value)["provider_extension"] is True


def test_original_json_text_is_forwarded_without_reformatting() -> None:
    body = (
        '{\n  "event_time": "2026-09-11T00:00:01.123Z",'
        '\n  "accuracy": 1.2300,\n  "memo": "원본"\n}\n'
    ).encode("utf-8")

    response, output = invoke_body(body)

    assert response.status_code == 202
    assert output.value == body.decode("utf-8")


def test_application_does_not_add_a_timestamp() -> None:
    payload = {"event_id": "evt_without_timestamp", "speed": None}

    response, output = invoke(payload)

    assert response.status_code == 202
    assert json.loads(output.value) == payload


def test_duplicate_event_id_retransmission_is_not_rejected_or_deduplicated() -> None:
    payload = synthetic_event()

    first_response, first_output = invoke(payload)
    second_response, second_output = invoke(payload)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert first_output.value == second_output.value


@pytest.mark.parametrize("payload", ([synthetic_event()], "gps", 42, None))
def test_any_parseable_json_value_is_accepted(payload: object) -> None:
    response, output = invoke(payload)

    assert response.status_code == 202
    assert json.loads(output.value) == payload


def test_invalid_json_returns_400() -> None:
    response, output = invoke_body(b"{invalid-json")

    assert response.status_code == 400
    assert response_json(response) == {"code": "invalid_json"}
    assert output.value is None
