"""Configuration and authentication; no Azure access until a handler needs it."""
import hashlib
import time
import hmac
import importlib
import json
import os
from functools import lru_cache
from .cosmos_service import CosmosTripStore, SQLiteTripStore
from .mock_trip_processor import MockTripProcessor
from .trip_service import ApiError, TripService


def local_mode():
    return os.getenv("APP_ENV") == "development" and not os.getenv("WEBSITE_HOSTNAME")


@lru_cache
def accounts():
    from .accounts import Accounts, CampaignRegistry
    return Accounts(user_registration().container, CampaignRegistry.from_env())


@lru_cache
def user_registration():
    if os.getenv("CANOPY_LOCAL_ONLY") == "true":
        if not local_mode():
            raise RuntimeError("Local accounts require development mode")
        from .local_documents import LocalDocuments
        from .user_registration import UserRegistration
        return UserRegistration(LocalDocuments(os.environ["CANOPY_LOCAL_USERS_PATH"]), os.environ["TRIP_CAMPAIGN_ID"])
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential
    from .user_registration import UserRegistration
    client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=DefaultAzureCredential())
    container = client.get_database_client(os.environ["COSMOS_TRIPS_DATABASE"]).get_container_client("users")
    if container.read()["partitionKey"]["paths"] != ["/user_id"]:
        raise RuntimeError("users partition key must be /user_id")
    return UserRegistration(container, os.environ["TRIP_CAMPAIGN_ID"])


@lru_cache
def feedback_service():
    # Lazy: feedback storage does not add initialization work to Trip stop.
    from .trip_feedback import CosmosFeedbackStore, SQLiteFeedbackStore, TripFeedbackService
    trips = service()
    if isinstance(trips.store, SQLiteTripStore):
        store = SQLiteFeedbackStore(trips.store.path + ".feedback")
    else:
        store = CosmosFeedbackStore(trips.store.client, os.environ["COSMOS_TRIPS_DATABASE"],
                                    os.environ.get("COSMOS_FEEDBACK_CONTAINER", "trip_feedback"))
    return TripFeedbackService(trips, store)


@lru_cache
def service():
    if os.getenv("TRIP_STORE") == "sqlite":
        if not local_mode():
            raise RuntimeError("SQLite is available only for local development")
        store = SQLiteTripStore(os.getenv("TRIP_SQLITE_PATH", ".local-data/trips.sqlite"))
    else:
        store = CosmosTripStore(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_TRIPS_DATABASE"],
                                os.environ["COSMOS_TRIPS_CONTAINER"])
    selection = os.environ.get("TRIP_PROCESSOR", "mock")
    if selection == "mock":
        processor = MockTripProcessor()
    else:
        # Trusted deployment configuration, never an HTTP parameter.
        module_name, class_name = selection.split(":", 1)
        processor = getattr(importlib.import_module(module_name), class_name)()
    campaign_id = os.environ["TRIP_CAMPAIGN_ID"]
    publisher = None
    if os.getenv("TRIP_END_EVENTS_ENABLED", "false").lower() == "true":
        from .trip_lifecycle import EventHubLifecyclePublisher
        publisher = EventHubLifecyclePublisher()
    if not campaign_id.strip():
        raise RuntimeError("TRIP_CAMPAIGN_ID is required")
    return TripService(store, processor, campaign_id=campaign_id, grace_seconds=int(os.getenv("TRIP_PROCESS_DELAY_SECONDS", "5")),
                       lease_seconds=int(os.getenv("TRIP_PROCESS_LEASE_SECONDS", "900")),
                       process_on_stop=os.getenv("TRIP_PROCESS_ON_STOP", "true").lower() == "true",
                       lifecycle_publisher=publisher, result_owner=os.getenv("TRIP_RESULT_OWNER", "functions"))


@lru_cache
def jwt_keys(url):
    import jwt
    if not url.startswith("https://"):
        raise RuntimeError("TRIP_JWKS_URL must use HTTPS")
    return jwt.PyJWKClient(url)


def authenticate(headers) -> str:
    authorization = headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "unauthorized", "login required")
    token = authorization[7:]
    if token.startswith("canopy1."):
        if os.getenv("CANOPY_ACCOUNT_AUTH_ENABLED", "false").lower() != "true":
            raise ApiError(503, "auth_unavailable", "계정 로그인이 아직 활성화되지 않았습니다.")
        return accounts().authenticated(token)["user_id"]
    if os.getenv("TRIP_AUTH_MODE", "jwt") == "test":
        # Explicit, expiring internal-test credentials; not registration or role assignment.
        if os.getenv("APP_ENV") != "test":
            raise ApiError(503, "configuration_error", "test authentication requires test environment")
        digest = hashlib.sha256(token.encode()).hexdigest()
        for user_id, entry in json.loads(os.environ.get("TRIP_TEST_CREDENTIALS", "{}")).items():
            if (isinstance(user_id, str) and 0 < len(user_id) <= 200 and isinstance(entry, dict)
                    and isinstance(entry.get("sha256"), str) and isinstance(entry.get("expires_at"), (int, float))
                    and entry["expires_at"] > time.time() and len(token) >= 32
                    and hmac.compare_digest(entry["sha256"], digest)):
                return user_id
        raise ApiError(401, "unauthorized", "invalid or expired test credential")
    if os.getenv("TRIP_AUTH_MODE", "jwt") == "local":
        if not local_mode():
            raise ApiError(503, "configuration_error", "local authentication is disabled on Azure")
        # Configured per-user credentials, never trust body.user_id or an arbitrary header.
        for user_id, secret in json.loads(os.environ.get("TRIP_LOCAL_TOKENS", "{}")).items():
            if isinstance(secret, str) and len(secret) >= 24 and hmac.compare_digest(secret, token):
                return user_id
        raise ApiError(401, "unauthorized", "invalid local test token")
    if os.getenv('CANOPY_ACCOUNT_AUTH_ENABLED','false').lower()=='true' and not os.getenv('TRIP_JWKS_URL'):
        raise ApiError(401,'unauthorized','invalid access token')
    import jwt
    issuer, audience, url = (os.environ[k] for k in ("TRIP_JWT_ISSUER", "TRIP_JWT_AUDIENCE", "TRIP_JWKS_URL"))
    try:
        key = jwt_keys(url).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=audience, issuer=issuer,
                            options={"require": ["exp", "iss", "aud", "sub"]})
        user_id = claims.get(os.getenv("TRIP_USER_ID_CLAIM", "sub"))
        if not isinstance(user_id, str) or not user_id or len(user_id) > 200:
            raise ApiError(401, "unauthorized", "invalid user identity")
        return user_id
    except jwt.PyJWTError as exc:
        raise ApiError(401, "unauthorized", "invalid or expired access token") from exc
