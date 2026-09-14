"""Configuration and authentication; no Azure access until a handler needs it."""
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
def service():
    if os.getenv("TRIP_STORE") == "sqlite":
        if not local_mode():
            raise RuntimeError("SQLite is available only for local development")
        store = SQLiteTripStore(os.getenv("TRIP_SQLITE_PATH", ".local-data/trips.sqlite"))
    else:
        store = CosmosTripStore(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_DATABASE"],
                                os.environ["COSMOS_TRIPS_CONTAINER"], os.environ["COSMOS_TRIPS_PARTITION_FIELD"])
    selection = os.environ.get("TRIP_PROCESSOR", "mock")
    if selection == "mock":
        processor = MockTripProcessor()
    else:
        # Trusted deployment configuration, never an HTTP parameter.
        module_name, class_name = selection.split(":", 1)
        processor = getattr(importlib.import_module(module_name), class_name)()
    return TripService(store, processor, grace_seconds=int(os.getenv("TRIP_PROCESS_DELAY_SECONDS", "5")),
                       lease_seconds=int(os.getenv("TRIP_PROCESS_LEASE_SECONDS", "900")))


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
    if os.getenv("TRIP_AUTH_MODE", "jwt") == "local":
        if not local_mode():
            raise ApiError(503, "configuration_error", "local authentication is disabled on Azure")
        # Configured per-user credentials, never trust body.user_id or an arbitrary header.
        for user_id, secret in json.loads(os.environ.get("TRIP_LOCAL_TOKENS", "{}")).items():
            if isinstance(secret, str) and len(secret) >= 24 and hmac.compare_digest(secret, token):
                return user_id
        raise ApiError(401, "unauthorized", "invalid local test token")
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
