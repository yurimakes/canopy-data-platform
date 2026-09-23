"""Pure helpers for Azure Event Hubs Kafka authentication."""

from __future__ import annotations


def normalized_policy_key(value: str) -> str:
    """Remove accidental terminal whitespace from a stored SAS policy key."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("Event Hubs SAS policy key is empty after normalization")
    return normalized


def connection_string(namespace: str, policy_name: str, policy_key: str) -> str:
    """Build the namespace-level Event Hubs connection string used by Kafka."""
    namespace = namespace.strip()
    policy_name = policy_name.strip()
    if not namespace:
        raise ValueError("Event Hubs namespace is empty")
    if not policy_name:
        raise ValueError("Event Hubs SAS policy name is empty")
    return (
        f"Endpoint=sb://{namespace}.servicebus.windows.net/;"
        f"SharedAccessKeyName={policy_name};"
        f"SharedAccessKey={normalized_policy_key(policy_key)}"
    )


def jaas_config(connection: str) -> str:
    """Build the Databricks-shaded Kafka PLAIN JAAS configuration."""
    escaped = connection.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required "
        'username="$ConnectionString" '
        f'password="{escaped}";'
    )
