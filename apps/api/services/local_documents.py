"""로컬 계정 저장. 기존 계정 검증과 ETag 충돌 처리 유지."""
from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError, CosmosHttpResponseError


class LocalDocuments:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, version INTEGER NOT NULL, body TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def read_item(self, item, partition_key=None):
        if partition_key is not None and partition_key != item:
            raise CosmosResourceNotFoundError(status_code=404, message='partition mismatch')
        with self.connect() as db:
            row = db.execute('SELECT version, body FROM documents WHERE id=?', (item,)).fetchone()
        if row is None:
            raise CosmosResourceNotFoundError(status_code=404, message='not found')
        return {**json.loads(row[1]), '_etag': str(row[0])}

    def create_item(self, body):
        try:
            with self.connect() as db:
                db.execute('INSERT INTO documents VALUES (?,1,?)', (body['id'], json.dumps(body)))
        except sqlite3.IntegrityError as exc:
            raise CosmosResourceExistsError(status_code=409, message='already exists') from exc
        return self.read_item(body['id'])

    def replace_item(self, item, body, etag=None, match_condition=None):
        with self.connect() as db:
            changed = db.execute('UPDATE documents SET body=?,version=version+1 WHERE id=? AND version=?',
                                 (json.dumps(body), item, int(etag))).rowcount
            if not changed:
                raise CosmosHttpResponseError(status_code=412, message='version conflict')
        return self.read_item(item)

    def all(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT body FROM documents')]
