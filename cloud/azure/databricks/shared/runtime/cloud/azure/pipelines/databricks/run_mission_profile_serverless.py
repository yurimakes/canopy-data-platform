"""Databricks Serverless entrypoint for Mission Profile.

`build_mission_profile.py` keeps the portable Azure runtime path based on
`DefaultAzureCredential`. Databricks Serverless cannot use the default service
credential environment-variable flow, so this entrypoint explicitly resolves a
Unity Catalog Service Credential and injects the resulting Cosmos clients for
this run only.
"""
from __future__ import annotations

import os
import sys

import build_mission_profile as mission_profile

SERVICE_CREDENTIAL_ENV = "CANOPY_DATABRICKS_SERVICE_CREDENTIAL_NAME"


def _serverless_cosmos_clients():
    if not mission_profile.COSMOS_ENDPOINT:
        return None, None

    credential_name = os.environ.get(SERVICE_CREDENTIAL_ENV)
    if not credential_name:
        raise RuntimeError(
            f"{SERVICE_CREDENTIAL_ENV} is required for Databricks Serverless Mission Profile runs"
        )

    from azure.cosmos import CosmosClient
    from databricks.sdk.runtime import dbutils

    credential = dbutils.credentials.getServiceCredentialsProvider(credential_name)
    client = CosmosClient(mission_profile.COSMOS_ENDPOINT, credential=credential)
    db = client.get_database_client(mission_profile.COSMOS_DATABASE)
    return (
        db.get_container_client(mission_profile.COSMOS_PROFILE_CONTAINER),
        db.get_container_client(mission_profile.COSMOS_MISSION_CONTAINER),
    )


def run(campaign_id: str, source_week_start: str, source_week_end: str):
    """Run Mission Profile with an explicit Databricks Service Credential."""
    original = mission_profile._cosmos_clients
    mission_profile._cosmos_clients = _serverless_cosmos_clients
    try:
        return mission_profile.run(campaign_id, source_week_start, source_week_end)
    finally:
        mission_profile._cosmos_clients = original


if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else None
    start = sys.argv[2] if len(sys.argv) > 2 else ""
    end = sys.argv[3] if len(sys.argv) > 3 else ""

    if not campaign:
        raise ValueError("campaign_id parameter required")
    if not start or not end:
        start, end = mission_profile.compute_last_completed_week()

    run(campaign, start, end)
