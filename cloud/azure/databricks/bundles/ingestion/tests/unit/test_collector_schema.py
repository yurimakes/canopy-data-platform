import hashlib
import json
from pathlib import Path
import unittest

from gps_ingestion.spark_ingestion import (
    REQUIRED_COLLECTOR_FIELDS,
    SUPPORTED_SCHEMA_VERSIONS,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "gps.collector.schema.json"
METADATA_PATH = ROOT / "schemas" / "gps.collector.schema.metadata.json"


class CollectorSchemaTest(unittest.TestCase):
    def test_vendored_schema_matches_pinned_hash(self) -> None:
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, metadata["sha256"])
        self.assertEqual(
            metadata["schema_introducing_commit"],
            "3acc91ec9ed40504f4b529219f7948c4057c09e9",
        )

    def test_parser_versions_and_required_fields_match_schema(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            tuple(schema["properties"]["schema_version"]["enum"]),
            SUPPORTED_SCHEMA_VERSIONS,
        )
        self.assertEqual(tuple(schema["required"]), REQUIRED_COLLECTOR_FIELDS)
        self.assertTrue(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
