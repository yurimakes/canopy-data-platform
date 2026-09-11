"""HTTP GPS ingestion function with an Azure Event Hubs output binding."""

from __future__ import annotations

import json
import logging
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


def _extract_core_fields(payload: Any) -> dict[str, Any]:
    return (
        {field: payload.get(field) for field in CORE_FIELDS}
        if isinstance(payload, dict)
        else {}
    )


def _json_response(payload: dict[str, Any], status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        status_code=status_code,
        mimetype="application/json",
    )


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
        logger.warning("GPS request rejected: body is not valid JSON")
        return _json_response({"code": "invalid_json"}, 400)

    core_fields = _extract_core_fields(payload)

    # Forward the original JSON text so Bronze ingestion does not drop fields,
    # coerce values, or add application-owned timestamps.
    event.set(req.get_body().decode("utf-8"))

    present_core_field_count = (
        sum(field in payload for field in CORE_FIELDS)
        if isinstance(payload, dict)
        else 0
    )
    logger.info(
        "GPS event accepted: core_fields_present=%d/%d",
        present_core_field_count,
        len(CORE_FIELDS),
    )
    return _json_response({"status": "accepted"}, 202)
