import json
import math

import azure.functions as func
import pytest

from function_app import CORE_FIELDS, gps_ingest


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


def invoke(payload: object) -> tuple[func.HttpResponse, FakeEventHubOutput]:
    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/gps",
        headers={"content-type": "application/json"},
        params={},
        route_params={},
        body=json.dumps(payload, allow_nan=True).encode("utf-8"),
    )
    output = FakeEventHubOutput()
    response = gps_ingest(request, output)
    return response, output


def response_json(response: func.HttpResponse) -> dict[str, object]:
    return json.loads(response.get_body())


def test_normal_synthetic_event_returns_202_and_sets_output() -> None:
    payload = synthetic_event()
    response, output = invoke(payload)

    assert response.status_code == 202
    assert response_json(response) == {
        "status": "accepted",
        "event_id": payload["event_id"],
        "trip_id": payload["trip_id"],
    }
    assert output.value is not None
    assert isinstance(output.value, str)
    assert json.loads(output.value) == payload


def test_null_speed_is_accepted_and_preserved() -> None:
    payload = synthetic_event()
    payload["speed"] = None

    response, output = invoke(payload)

    assert response.status_code == 202
    assert json.loads(output.value)["speed"] is None


@pytest.mark.parametrize(("field", "value"), (("lat", 91), ("lon", 181)))
def test_out_of_range_coordinate_returns_400(field: str, value: int) -> None:
    payload = synthetic_event()
    payload[field] = value

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {"code": "out_of_range", "field": field}
    assert output.value is None


def test_required_key_missing_returns_400() -> None:
    payload = synthetic_event()
    del payload["accuracy"]

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {
        "code": "missing_required_field",
        "field": "accuracy",
    }
    assert output.value is None


def test_speed_key_missing_returns_400_without_defaulting_to_zero() -> None:
    payload = synthetic_event()
    del payload["speed"]

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {
        "code": "missing_required_field",
        "field": "speed",
    }
    assert output.value is None


def test_string_speed_returns_400() -> None:
    payload = synthetic_event()
    payload["speed"] = "1.25"

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {"code": "invalid_number", "field": "speed"}
    assert output.value is None


def test_boolean_sequence_returns_400() -> None:
    payload = synthetic_event()
    payload["sequence"] = True

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {
        "code": "invalid_integer",
        "field": "sequence",
    }
    assert output.value is None


@pytest.mark.parametrize("field", ("lat", "lon", "accuracy", "speed"))
def test_boolean_number_fields_return_400(field: str) -> None:
    payload = synthetic_event()
    payload[field] = False

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {"code": "invalid_number", "field": field}
    assert output.value is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("lat", math.nan),
        ("lon", math.inf),
        ("accuracy", -math.inf),
        ("speed", math.nan),
    ),
)
def test_non_finite_numbers_return_400(field: str, value: float) -> None:
    payload = synthetic_event()
    payload[field] = value

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {"code": "invalid_number", "field": field}
    assert output.value is None


def test_extra_fields_are_excluded_from_event_hub_payload() -> None:
    payload = synthetic_event()
    payload["device_id"] = "device_unit_01"
    payload["raw_location"] = {"synthetic": True}

    response, output = invoke(payload)

    assert response.status_code == 202
    event_payload = json.loads(output.value)
    assert set(event_payload) == set(CORE_FIELDS)
    assert "device_id" not in event_payload
    assert "raw_location" not in event_payload


def test_identifiers_are_preserved_in_response_and_output() -> None:
    payload = synthetic_event()
    payload["event_id"] = "evt_preserve_0099"
    payload["trip_id"] = "trip_preserve_0099"

    response, output = invoke(payload)

    assert response.status_code == 202
    body = response_json(response)
    event_payload = json.loads(output.value)
    assert body["event_id"] == payload["event_id"]
    assert body["trip_id"] == payload["trip_id"]
    assert event_payload["event_id"] == payload["event_id"]
    assert event_payload["trip_id"] == payload["trip_id"]


def test_duplicate_event_id_retransmission_is_not_rejected_or_deduplicated() -> None:
    payload = synthetic_event()

    first_response, first_output = invoke(payload)
    second_response, second_output = invoke(payload)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert first_output.value == second_output.value


@pytest.mark.parametrize("field", ("event_id", "user_id", "trip_id", "event_time", "schema_version"))
def test_empty_string_fields_return_400(field: str) -> None:
    payload = synthetic_event()
    payload[field] = "   "

    response, output = invoke(payload)

    assert response.status_code == 400
    assert response_json(response) == {"code": "invalid_type_or_empty", "field": field}
    assert output.value is None


def test_json_array_returns_400() -> None:
    response, output = invoke([synthetic_event()])

    assert response.status_code == 400
    assert response_json(response) == {"code": "invalid_json_object"}
    assert output.value is None


def test_invalid_json_returns_400() -> None:
    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/gps",
        headers={"content-type": "application/json"},
        params={},
        route_params={},
        body=b"{invalid-json",
    )
    output = FakeEventHubOutput()

    response = gps_ingest(request, output)

    assert response.status_code == 400
    assert response_json(response) == {"code": "invalid_json"}
    assert output.value is None
