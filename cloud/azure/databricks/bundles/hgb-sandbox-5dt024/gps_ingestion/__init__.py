"""Canopy generic ingestion package."""

from .deployment_config import EventIngestionTableConfig
from .event_hubs_auth import connection_string, jaas_config, normalized_policy_key

__all__ = [
    "EventIngestionTableConfig",
    "connection_string",
    "jaas_config",
    "normalized_policy_key",
]
