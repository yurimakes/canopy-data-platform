"""Optimistic concurrency for existing Cosmos containers; no resource creation."""
import json
import sqlite3
from pathlib import Path
from typing import Protocol


class Conflict(Exception):
    pass


class TripStore(Protocol):
    def read(self, trip_id: str, user_id: str) -> dict | None: ...
    def create(self, item: dict) -> dict: ...
    def replace(self, item: dict) -> dict: ...
    def pending(self, now: str, limit: int = 20) -> list[dict]: ...


class CosmosTripStore:
    def __init__(self, endpoint: str, database: str, container: str, partition_field: str):
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential
        if partition_field not in ("user_id", "pk", "trip_id"):
            raise ValueError("Trip partition must be confirmed as /user_id, /pk or /trip_id")
        self.partition_field = partition_field
        self.client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        self.container = self.client.get_database_client(database).get_container_client(container)
        if self.container.read()["partitionKey"]["paths"] != ["/" + partition_field]:
            raise ValueError("configured Trip partition key differs from the existing container")

    def key(self, trip_id: str, user_id: str) -> str:
        return trip_id if self.partition_field == "trip_id" else user_id

    def read(self, trip_id: str, user_id: str) -> dict | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            return self.container.read_item(trip_id, partition_key=self.key(trip_id, user_id))
        except CosmosResourceNotFoundError:
            return None

    def create(self, item: dict) -> dict:
        from azure.cosmos.exceptions import CosmosResourceExistsError
        body = dict(item)
        body[self.partition_field] = self.key(item["trip_id"], item["user_id"])
        try:
            return self.container.create_item(body)
        except CosmosResourceExistsError as exc:
            raise Conflict from exc

    def replace(self, item: dict) -> dict:
        from azure.core import MatchConditions
        from azure.cosmos.exceptions import CosmosHttpResponseError
        try:
            return self.container.replace_item(item["id"], item, etag=item["_etag"],
                                               match_condition=MatchConditions.IfNotModified)
        except CosmosHttpResponseError as exc:
            if exc.status_code in (409, 412):
                raise Conflict from exc
            raise

    def pending(self, now: str, limit: int = 20) -> list[dict]:
        return list(self.container.query_items(
            query=f"SELECT TOP {int(limit)} * FROM c WHERE c.type = 'trip' AND c.status = 'processing' "
                  "AND c.process_after <= @now AND c.lease_until <= @now",
            parameters=[{"name": "@now", "value": now}], enable_cross_partition_query=True))


class SQLiteTripStore:
    """Durable local substitute implementing the same create/CAS contract."""
    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def read(self, trip_id: str, user_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT version,payload FROM trips WHERE id=?", (trip_id,)).fetchone()
        if not row:
            return None
        return {**json.loads(row[1]), "_etag": str(row[0])}

    def create(self, item: dict) -> dict:
        try:
            with self.connect() as db:
                db.execute("INSERT INTO trips VALUES (?,1,?)", (item["id"], json.dumps(item)))
        except sqlite3.IntegrityError as exc:
            raise Conflict from exc
        return {**item, "_etag": "1"}

    def replace(self, item: dict) -> dict:
        version = int(item["_etag"])
        with self.connect() as db:
            changed = db.execute("UPDATE trips SET version=version+1,payload=? WHERE id=? AND version=?",
                                 (json.dumps(item), item["id"], version)).rowcount
            if not changed:
                raise Conflict
        return {**item, "_etag": str(version + 1)}

    def pending(self, now: str, limit: int = 20) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT version,payload FROM trips WHERE json_extract(payload,'$.status')='processing' "
                              "AND json_extract(payload,'$.process_after')<=? "
                              "AND json_extract(payload,'$.lease_until')<=? LIMIT ?", (now, now, limit)).fetchall()
        return [{**json.loads(payload), "_etag": str(version)} for version, payload in rows]
