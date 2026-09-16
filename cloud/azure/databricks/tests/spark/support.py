import json
from pathlib import Path
import unittest

try:
    from pyspark.sql import SparkSession
except ImportError:
    SparkSession = None


SPARK_AVAILABLE = SparkSession is not None
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class SparkTestCase(unittest.TestCase):
    spark = None

    @classmethod
    def setUpClass(cls):
        if not SPARK_AVAILABLE:
            raise unittest.SkipTest("optional PySpark test dependency is not installed")
        try:
            cls.spark = (
                SparkSession.builder.master("local[2]")
                .appName("canopy-gps-ingestion-tests")
                .config("spark.ui.enabled", "false")
                .config("spark.sql.session.timeZone", "UTC")
                .getOrCreate()
            )
        except Exception as exc:
            raise unittest.SkipTest(f"local Spark runtime unavailable: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        if cls.spark is not None:
            cls.spark.stop()

    def bronze_frame(self, bodies):
        from datetime import datetime, timezone

        rows = [
            (
                body,
                "evh-canopy-gps-dev",
                3,
                101 + index,
                datetime(2026, 9, 16, 4, index, tzinfo=timezone.utc),
                datetime(2026, 9, 16, 4, index, 1, tzinfo=timezone.utc),
            )
            for index, body in enumerate(bodies)
        ]
        return self.spark.createDataFrame(
            rows,
            "body string, event_hub_topic string, event_hub_partition int, "
            "event_hub_offset long, event_hub_enqueued_at timestamp, ingested_at timestamp",
        )

    def parsed_payload(self, payload):
        from gps_ingestion.spark_ingestion import parse_bronze_rows

        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return parse_bronze_rows(self.bronze_frame([body])).collect()[0]
