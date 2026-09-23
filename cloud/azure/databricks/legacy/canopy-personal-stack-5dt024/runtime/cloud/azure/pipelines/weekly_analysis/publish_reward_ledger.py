"""Publish one explicit Weekly Reward scope and refresh its Gold ledger history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


DATABRICKS_MODULE_PATH = Path(__file__).resolve().parents[1] / "databricks"
if str(DATABRICKS_MODULE_PATH) not in sys.path:
    sys.path.insert(0, str(DATABRICKS_MODULE_PATH))

import reward_ledger


def _resolved(value: str, name: str) -> str:
    value = (value or "").strip()
    if not value or "{{" in value:
        raise ValueError(f"Resolved {name} required")
    return value


def _get_container(endpoint: str, secret_scope: str, secret_key: str):
    from azure.cosmos import CosmosClient
    from databricks.sdk.runtime import dbutils

    credential = dbutils.secrets.get(
        scope=secret_scope,
        key=secret_key,
    )
    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(reward_ledger.COSMOS_DATABASE)
    return database.get_container_client(
        reward_ledger.COSMOS_REWARD_LEDGER_CONTAINER
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--reward-calc-source", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--secret-scope", required=True)
    parser.add_argument("--secret-key", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    campaign_id = _resolved(args.campaign_id, "campaign_id")
    week = _resolved(args.week, "week")
    reward_calc_source = _resolved(
        args.reward_calc_source,
        "reward_calc_source",
    )
    endpoint = _resolved(args.endpoint, "endpoint")
    secret_scope = _resolved(args.secret_scope, "secret_scope")
    secret_key = _resolved(args.secret_key, "secret_key")

    container = _get_container(endpoint, secret_scope, secret_key)
    return reward_ledger.run(
        campaign_id,
        week,
        reward_calc_source,
        container=container,
    )


if __name__ == "__main__":
    main()
