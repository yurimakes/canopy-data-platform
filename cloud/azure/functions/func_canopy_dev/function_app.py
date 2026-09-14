import json
import logging
import os
import uuid
from datetime import datetime, timezone

import azure.functions as func

from azure.identity import DefaultAzureCredential
from azure.eventhub import EventHubProducerClient, EventData
from azure.cosmos import CosmosClient
from azure.keyvault.secrets import SecretClient


app = func.FunctionApp()


# ---------------------------------------------------------
# 1. Function 자체 + Application Insights 검증
# ---------------------------------------------------------
@app.route(
    route="health",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION
)
def health(req: func.HttpRequest) -> func.HttpResponse:

    logging.info("canopy_health_check_ok")

    return func.HttpResponse(
        json.dumps({
            "status": "ok",
            "service": "canopy-api"
        }),
        status_code=200,
        mimetype="application/json"
    )


# ---------------------------------------------------------
# 2. Function -> Event Hubs Managed Identity 검증
# ---------------------------------------------------------
@app.route(
    route="gps-smoke",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def gps_smoke(req: func.HttpRequest) -> func.HttpResponse:

    try:
        body = req.get_json()

        required = [
            "event_id",
            "trip_id",
            "event_time",
            "sequence"
        ]

        missing = [key for key in required if key not in body]

        if missing:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "missing_fields": missing
                }),
                status_code=400,
                mimetype="application/json"
            )

        credential = DefaultAzureCredential()

        producer = EventHubProducerClient(
            fully_qualified_namespace=os.environ["EVENTHUB_FQDN"],
            eventhub_name=os.environ["EVENTHUB_NAME"],
            credential=credential
        )

        event = EventData(json.dumps(body))

        with producer:
            batch = producer.create_batch(
                partition_key=body["trip_id"]
            )
            batch.add(event)
            producer.send_batch(batch)

        logging.info(
            "gps_publish_success event_id=%s trip_id=%s",
            body["event_id"],
            body["trip_id"]
        )

        return func.HttpResponse(
            json.dumps({
                "status": "accepted",
                "event_id": body["event_id"],
                "trip_id": body["trip_id"]
            }),
            status_code=202,
            mimetype="application/json"
        )

    except Exception as e:

        logging.exception("gps_publish_failed")

        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error_type": type(e).__name__,
                "message": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )


# ---------------------------------------------------------
# 3. Function -> Cosmos DB Managed Identity 검증
# ---------------------------------------------------------
@app.route(
    route="cosmos-smoke",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def cosmos_smoke(req: func.HttpRequest) -> func.HttpResponse:

    try:

        credential = DefaultAzureCredential()

        client = CosmosClient(
            os.environ["COSMOS_ENDPOINT"],
            credential=credential
        )

        database = client.get_database_client(
            os.environ["COSMOS_DATABASE"]
        )

        container = database.get_container_client(
            os.environ["COSMOS_CONTAINER"]
        )

        test_id = "cosmos-smoke-" + str(uuid.uuid4())

        item = {
            "id": test_id,
            "pk": "smoke",
            "status": "PASS",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        container.upsert_item(item)

        saved = container.read_item(
            item=test_id,
            partition_key="smoke"
        )

        logging.info(
            "cosmos_smoke_success item_id=%s",
            test_id
        )

        return func.HttpResponse(
            json.dumps({
                "status": "PASS",
                "written_id": test_id,
                "read_back_status": saved["status"]
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:

        logging.exception("cosmos_smoke_failed")

        return func.HttpResponse(
            json.dumps({
                "status": "FAIL",
                "error_type": type(e).__name__,
                "message": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )


# ---------------------------------------------------------
# 4. Function -> Key Vault Managed Identity 검증
# ---------------------------------------------------------
@app.route(
    route="keyvault-smoke",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION
)
def keyvault_smoke(req: func.HttpRequest) -> func.HttpResponse:

    try:

        credential = DefaultAzureCredential()

        client = SecretClient(
            vault_url=os.environ["KEYVAULT_URI"],
            credential=credential
        )

        secret = client.get_secret(
            os.environ["KEYVAULT_TEST_SECRET"]
        )

        # Secret 값 자체는 절대 응답/로그에 출력하지 않는다.
        logging.info("keyvault_secret_read_success")

        return func.HttpResponse(
            json.dumps({
                "status": "PASS",
                "secret_loaded": secret.value is not None
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:

        logging.exception("keyvault_smoke_failed")

        return func.HttpResponse(
            json.dumps({
                "status": "FAIL",
                "error_type": type(e).__name__,
                "message": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )
# ---------------------------------------------------------
# 5. GPS Bronze ingestion -> Event Hubs
# ---------------------------------------------------------

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


def _extract_core_fields(payload):
    return (
        {field: payload.get(field) for field in CORE_FIELDS}
        if isinstance(payload, dict)
        else {}
    )


def _gps_json_response(payload, status_code):
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        status_code=status_code,
        mimetype="application/json",
    )


@app.function_name(name="GpsIngest")
@app.route(
    route="gps",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
@app.event_hub_output(
    arg_name="event",
    event_hub_name="%EVENTHUB_NAME%",
    connection="EVENTHUB",
)
def gps_ingest(req: func.HttpRequest, event: func.Out[str]) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        logging.warning("GPS request rejected: body is not valid JSON")
        return _gps_json_response({"code": "invalid_json"}, 400)

    _extract_core_fields(payload)

    event.set(req.get_body().decode("utf-8"))

    present_core_field_count = (
        sum(field in payload for field in CORE_FIELDS)
        if isinstance(payload, dict)
        else 0
    )

    logging.info(
        "GPS event accepted: core_fields_present=%d/%d",
        present_core_field_count,
        len(CORE_FIELDS),
    )

    return _gps_json_response({"status": "accepted"}, 202)
