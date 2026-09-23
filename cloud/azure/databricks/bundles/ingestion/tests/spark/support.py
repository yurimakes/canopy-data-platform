from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

import pytest

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class SparkTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SparkSession is None:
            raise unittest.SkipTest("pyspark is not installed")
        try:
            cls.spark = (
                SparkSession.builder.master("local[2]")
                .appName("canopy-gps-ingestion-tests")
                .config("spark.ui.enabled", "false")
                .config("spark.sql.session.timeZone", "UTC")
                .getOrCreate()
            )
            probe = cls.spark.sql("select try_parse_json('{\"x\":1}') as payload")
            probe.collect()
        except Exception as exc:
            if getattr(cls, "spark", None) is not None:
                cls.spark.stop()
            raise unittest.SkipTest(f"local Spark 4 VARIANT runtime unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "spark", None) is not None:
            cls.spark.stop()

    def bronze_frame(self, bodies):
        now = datetime(2026, 9, 16, 1, 2, 3, tzinfo=timezone.utc)
        return self.spark.createDataFrame(
            [
                (body, "evh-canopy-gps-dev", 3, 101 + i, now, now)
                for i, body in enumerate(bodies)
            ],
            "body string, event_hub_topic string, event_hub_partition int, "
            "event_hub_offset long, event_hub_enqueued_at timestamp, ingested_at timestamp",
        )

    def generic_bronze_frame(self, bodies):
        now = datetime(2026, 9, 18, 1, 2, 3, tzinfo=timezone.utc)
        rows = []
        for i, body in enumerate(bodies):
            payload = json.loads(body)
            rows.append(
                (
                    body,
                    payload.get("event_id"),
                    payload.get("event_type"),
                    payload.get("schema_version"),
                    "evh-canopy-gps-dev",
                    3,
                    201 + i,
                    now,
                    now,
                )
            )
        return self.spark.createDataFrame(
            rows,
            "raw_payload string, event_id string, event_type string, schema_version string, "
            "event_hub_topic string, event_hub_partition int, event_hub_offset long, "
            "event_hub_enqueued_at timestamp, ingested_at timestamp",
        )
