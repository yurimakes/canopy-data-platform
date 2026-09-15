from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class BaselineRuntimeConfigError(ValueError):
    """Raised when runtime-only storage or Cosmos configuration is incomplete."""


DEFAULT_WEEKLY_USER_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/weekly_summary_user/"
)
DEFAULT_PERSONAL_HISTORY_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/personal_baseline_history/"
)
DEFAULT_GLOBAL_HISTORY_PATH = (
    "abfss://curated@stcanopydev5dt.dfs.core.windows.net/gold/global_baseline_history/"
)


def _value(
    explicit: str | None,
    env_key: str,
    *,
    environ: Mapping[str, str] | None = None,
    aliases: tuple[str, ...] = (),
) -> str | None:
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    source = environ if environ is not None else os.environ
    for key in (env_key, *aliases):
        value = source.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _required(name: str, value: str | None) -> str:
    if not value:
        raise BaselineRuntimeConfigError(f"Missing runtime setting: {name}")
    return value


@dataclass(frozen=True)
class BaselineGoldPaths:
    weekly_user: str
    personal_history: str
    global_history: str
    eligibility: str | None = None


@dataclass(frozen=True)
class CosmosIdentityConfig:
    endpoint: str
    database: str
    subscription_id: str
    tenant_id: str
    resource_group_name: str
    managed_identity_client_id: str
    throughput_threshold: str = "0.30"


@dataclass(frozen=True)
class CosmosBaselineTargets:
    personal_container: str
    global_container: str


def load_gold_paths(
    *,
    weekly_user: str | None = None,
    personal_history: str | None = None,
    global_history: str | None = None,
    eligibility: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> BaselineGoldPaths:
    """Resolve the canonical Gold paths merged by the weekly-summary teammate.

    Environment variables still override the defaults so a future ADLS layout change
    does not require calculation-code changes. Eligibility is intentionally optional:
    its producer is owned by a separate teammate task and will be wired after that
    contract lands in main.
    """
    return BaselineGoldPaths(
        weekly_user=(
            _value(weekly_user, "CANOPY_GOLD_WEEKLY_USER_PATH", environ=environ)
            or DEFAULT_WEEKLY_USER_PATH
        ),
        personal_history=(
            _value(
                personal_history,
                "CANOPY_GOLD_PERSONAL_BASELINE_PATH",
                environ=environ,
            )
            or DEFAULT_PERSONAL_HISTORY_PATH
        ),
        global_history=(
            _value(
                global_history,
                "CANOPY_GOLD_GLOBAL_BASELINE_PATH",
                environ=environ,
            )
            or DEFAULT_GLOBAL_HISTORY_PATH
        ),
        eligibility=_value(
            eligibility,
            "CANOPY_BASELINE_ELIGIBILITY_PATH",
            environ=environ,
        ),
    )


def load_cosmos_identity(
    *,
    environ: Mapping[str, str] | None = None,
) -> CosmosIdentityConfig:
    """Resolve passwordless Cosmos Spark-connector settings."""
    return CosmosIdentityConfig(
        endpoint=_required(
            "CANOPY_COSMOS_ENDPOINT",
            _value(
                None,
                "CANOPY_COSMOS_ENDPOINT",
                aliases=("COSMOS_ENDPOINT",),
                environ=environ,
            ),
        ),
        database=_required(
            "CANOPY_COSMOS_DATABASE",
            _value(None, "CANOPY_COSMOS_DATABASE", environ=environ),
        ),
        subscription_id=_required(
            "CANOPY_AZURE_SUBSCRIPTION_ID",
            _value(None, "CANOPY_AZURE_SUBSCRIPTION_ID", environ=environ),
        ),
        tenant_id=_required(
            "CANOPY_AZURE_TENANT_ID",
            _value(None, "CANOPY_AZURE_TENANT_ID", environ=environ),
        ),
        resource_group_name=_required(
            "CANOPY_AZURE_RESOURCE_GROUP",
            _value(None, "CANOPY_AZURE_RESOURCE_GROUP", environ=environ),
        ),
        managed_identity_client_id=_required(
            "CANOPY_COSMOS_MI_CLIENT_ID",
            _value(None, "CANOPY_COSMOS_MI_CLIENT_ID", environ=environ),
        ),
        throughput_threshold=(
            _value(None, "CANOPY_COSMOS_THROUGHPUT_THRESHOLD", environ=environ)
            or "0.30"
        ),
    )


def load_cosmos_targets(
    *,
    environ: Mapping[str, str] | None = None,
) -> CosmosBaselineTargets:
    return CosmosBaselineTargets(
        personal_container=_required(
            "CANOPY_COSMOS_PERSONAL_BASELINE_CONTAINER",
            _value(
                None,
                "CANOPY_COSMOS_PERSONAL_BASELINE_CONTAINER",
                environ=environ,
            ),
        ),
        global_container=_required(
            "CANOPY_COSMOS_GLOBAL_BASELINE_CONTAINER",
            _value(
                None,
                "CANOPY_COSMOS_GLOBAL_BASELINE_CONTAINER",
                environ=environ,
            ),
        ),
    )


def build_cosmos_spark_options(
    identity: CosmosIdentityConfig,
    *,
    container: str,
) -> dict[str, str]:
    """Build Azure Cosmos DB Spark connector options using Managed Identity only."""
    return {
        "spark.cosmos.accountEndpoint": identity.endpoint,
        "spark.cosmos.database": identity.database,
        "spark.cosmos.container": container,
        "spark.cosmos.auth.type": "ManagedIdentity",
        "spark.cosmos.auth.aad.clientId": identity.managed_identity_client_id,
        "spark.cosmos.account.subscriptionId": identity.subscription_id,
        "spark.cosmos.account.tenantId": identity.tenant_id,
        "spark.cosmos.account.resourceGroupName": identity.resource_group_name,
        "spark.cosmos.throughputControl.enabled": "true",
        "spark.cosmos.throughputControl.name": "CanopyBaselinePublisher",
        "spark.cosmos.throughputControl.targetThroughputThreshold": identity.throughput_threshold,
        "spark.cosmos.throughputControl.globalControl.useDedicatedContainer": "false",
        "spark.cosmos.write.strategy": "ItemOverwrite",
        "spark.cosmos.write.bulk.enabled": "true",
    }
