"""HTTP GPS ingestion function with an Azure Event Hubs output binding."""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import azure.functions as func


app = func.FunctionApp()
logger = logging.getLogger("GpsIngest")

CORE_FIELDS = (
    "event_id",
    "user_id",
    "trip_id",
    "event_time",
    "lat",
    "lon",
    "accuracy",
    "speed",
    "sequence",
    "schema_version",
)

STRING_FIELDS = ("event_id", "user_id", "trip_id", "event_time", "schema_version")
NUMBER_FIELDS = ("lat", "lon", "accuracy")


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _json_response(payload: dict[str, Any], status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        status_code=status_code,
        mimetype="application/json",
    )


def _validation_error(code: str, field: str | None = None) -> func.HttpResponse:
    payload: dict[str, Any] = {"code": code}
    if field is not None:
        payload["field"] = field
    logger.warning("GPS request rejected: code=%s field=%s", code, field)
    return _json_response(payload, 400)


def _validate(payload: dict[str, Any]) -> tuple[str, str] | None:
    for field in CORE_FIELDS:
        if field not in payload:
            return "missing_required_field", field

    for field in STRING_FIELDS:
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            return "invalid_type_or_empty", field

    for field in NUMBER_FIELDS:
        if not _is_finite_number(payload[field]):
            return "invalid_number", field

    if not -90 <= payload["lat"] <= 90:
        return "out_of_range", "lat"
    if not -180 <= payload["lon"] <= 180:
        return "out_of_range", "lon"

    speed = payload["speed"]
    if speed is not None and not _is_finite_number(speed):
        return "invalid_number", "speed"

    sequence = payload["sequence"]
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        return "invalid_integer", "sequence"

    return None


@app.function_name(name="GpsIngest")
@app.route(route="gps", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
@app.event_hub_output(
    arg_name="event",
    event_hub_name="%EVENTHUB_NAME%",
    connection="EVENTHUB",
)
def gps_ingest(req: func.HttpRequest, event: func.Out[str]) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        return _validation_error("invalid_json")

    if not isinstance(payload, dict):
        return _validation_error("invalid_json_object")

    validation_error = _validate(payload)
    if validation_error is not None:
        return _validation_error(*validation_error)

    canonical_payload = {field: payload[field] for field in CORE_FIELDS}
    event.set(
        json.dumps(
            canonical_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    logger.info(
        "GPS event accepted: event_id=%s trip_id=%s",
        payload["event_id"],
        payload["trip_id"],
    )
    return _json_response(
        {
            "status": "accepted",
            "event_id": payload["event_id"],
            "trip_id": payload["trip_id"],
        },
        202,
    )
