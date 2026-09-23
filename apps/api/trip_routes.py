"""Trip HTTP routes and durable worker, registered into the existing Function App."""
import json
import logging
import re
import os
from typing import List
import azure.functions as func
from services.runtime import authenticate, service, feedback_service, user_registration, accounts
from services.trip_service import ApiError, public

bp = func.Blueprint()


def dispatch(method, path, headers, raw, trip_service=None, auth=authenticate, feedback_api=None, registration_api=None, account_api=None):
    try:
        headers = {key.lower(): value for key, value in headers.items()}
        limit = 262144 if path.endswith("/confirm") else 16384
        if len(raw) > limit:
            raise ApiError(413, "payload_too_large", "Trip request exceeds the size limit")
        try:
            body = json.loads(raw) if raw else {}
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, "invalid_json", "body must be JSON") from exc
        if not isinstance(body, dict):
            raise ApiError(400, "invalid_json", "body must be a JSON object")
        if path.startswith("/api/auth/"):
            if account_api is None and os.getenv("CANOPY_ACCOUNT_AUTH_ENABLED", "false").lower() != "true":
                raise ApiError(503, "auth_unavailable", "계정 로그인이 아직 활성화되지 않았습니다.")
            account = account_api or accounts()
            if method == "POST" and path == "/api/auth/signup":
                return 201, account.signup(body)
            if method == "POST" and path == "/api/auth/login":
                return 200, account.login(body)
            token = headers.get("authorization", "").removeprefix("Bearer ")
            doc = account.authenticated(token)
            if method == "GET" and path == "/api/auth/me":
                return 200, account.public(doc)
            if method == "PATCH" and path == "/api/auth/me":
                return 200, account.update(token, body)
            if method == "POST" and path == "/api/auth/logout":
                account.logout(token)
                return 200, {"status": "signed_out"}
            if method == "GET" and path == "/api/auth/developer":
                if doc.get("role") != "developer":
                    raise ApiError(403, "forbidden", "개발자 계정이 필요합니다.")
                return 200, {"role": "developer"}
            raise ApiError(404, "not_found", "route not found")
        user_id = auth(headers)
        if method == "POST" and path == "/api/users/register":
            result, created = (registration_api or user_registration()).register(user_id, body)
            return (201 if created else 200), result
        if method == "POST" and path == "/api/routes/transit":
            from services.transit_routes import transit_routes
            return 200, transit_routes(user_id, body)
        if method == "POST" and path == "/api/routes/places":
            from services.transit_routes import search_places
            return 200, search_places(user_id, body)
        api = trip_service or service()
        if method == "POST" and path == "/api/trips/start":
            if headers.get("authorization", "").startswith("Bearer canopy1."):
                doc = (account_api or accounts()).authenticated(headers["authorization"][7:])
                if not doc.get("campaign_id") or doc.get("campaign_left_at"):
                    raise ApiError(403, "campaign_required", "참여 중인 캠페인이 필요합니다.")
                if "campaign_id" in body and body["campaign_id"] != doc["campaign_id"]:
                    raise ApiError(403, "campaign_mismatch", "가입한 캠페인으로만 여정을 시작할 수 있습니다.")
                trip, created = api.start(user_id, body, campaign_id=doc["campaign_id"])
            else:
                trip, created = api.start(user_id, body)
            return (201 if created else 200), public(trip)
        match = re.fullmatch(r"/api/trips/([a-zA-Z0-9_-]{1,100})(/stop|/confirm|/feedback)?", path)
        if not match:
            raise ApiError(404, "not_found", "route not found")
        trip_id, stop = match.groups()
        if stop == "/feedback" and method == "POST":
            return 200, public((feedback_api or feedback_service()).submit(trip_id, user_id, body))
        if stop == "/confirm" and method == "POST":
            api.get(trip_id, user_id)  # Preserve ownership checks for old app versions.
            raise ApiError(410, "correction_retired", "Direct correction is retired; submit Trip feedback instead")
        if stop == "/stop" and method == "POST":
            trip = api.stop(trip_id, user_id, body)
            if os.getenv("TRIP_DATABRICKS_ENABLED", "false").lower() == "true":
                try:
                    from services.trip_dispatch import recover
                    recover(api.store)
                except Exception as exc:
                    logging.warning("trip_dispatch_deferred trip_id=%s error_type=%s", trip_id, type(exc).__name__)
            return (202 if trip["status"] == "processing" else 200), public(trip)
        if not stop and method == "GET":
            return 200, public(api.get(trip_id, user_id))
        raise ApiError(405, "method_not_allowed", "method not allowed")
    except ApiError as exc:
        return exc.status, {"status": exc.code, "message": str(exc)}
    except Exception as exc:
        logging.error("trip_request_failed error_type=%s", type(exc).__name__)
        return 503, {"status": "service_unavailable", "message": "Trip service configuration or storage unavailable"}


def response(req):
    from urllib.parse import urlsplit
    status, body = dispatch(req.method, urlsplit(req.url).path, req.headers, req.get_body())
    return func.HttpResponse(json.dumps(body, ensure_ascii=False), status_code=status, mimetype="application/json",
                             headers={"Cache-Control": "no-store"})


@bp.route(route="auth/{action}", methods=["GET", "POST", "PATCH"], auth_level=func.AuthLevel.FUNCTION)
def account_auth(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="users/register", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def user_register(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="trips/start", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def trip_start(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="routes/places", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def place_search(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="routes/transit", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def transit_route_search(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="trips/{trip_id}/stop", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def trip_stop(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="trips/{trip_id}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def trip_get(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="trips/{trip_id}/confirm", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def trip_confirm(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.route(route="trips/{trip_id}/feedback", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def trip_feedback(req: func.HttpRequest) -> func.HttpResponse:
    return response(req)


@bp.timer_trigger(schedule="%TRIP_WORKER_SCHEDULE%", arg_name="timer", run_on_startup=False, use_monitor=True)
def trip_worker(timer: func.TimerRequest) -> None:
    # Cosmos processing documents are the outbox: stop + scheduling is a single CAS write.
    service().process_pending()
    if os.getenv("TRIP_DATABRICKS_ENABLED", "false").lower() == "true":
        from services.trip_dispatch import recover
        recover(service().store)
    try:
        feedback_service().recover_pending()
    except Exception as exc:
        logging.error("feedback_recovery_failed error_type=%s", type(exc).__name__)


if os.getenv("TRIP_DATABRICKS_ENABLED", "false").lower() == "true":
    @bp.retry(strategy="exponential_backoff", max_retry_count="5", minimum_interval="00:00:05", maximum_interval="00:01:00")
    @bp.event_hub_message_trigger(arg_name="events", connection="TRIP_EVENTHUB", event_hub_name="%EVENTHUB_NAME%",
                                  consumer_group="%TRIP_EVENTHUB_CONSUMER_GROUP%", cardinality="many")
    def trip_end_received(events: List[func.EventHubEvent]):
        from services.trip_dispatch import receive, recover
        store = service().store
        accepted = False
        for event in events:
            try:
                payload = json.loads(event.get_body().decode("utf-8"))
            except (ValueError, UnicodeError):
                continue
            if isinstance(payload, dict) and payload.get("event_type") == "trip_ended":
                accepted = receive(store, payload) or accepted
        if accepted:
            recover(store)
