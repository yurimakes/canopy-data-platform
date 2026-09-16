from datetime import datetime, timezone

from gps_ingestion.spark_ingestion import bronze_rows
from tests.spark.support import SparkTestCase


class BronzeProjectionTest(SparkTestCase):
    def test_body_and_event_hubs_coordinates_are_projected_without_reserialization(self):
        body = '{\n  "memo": "서울", "number": 1.2300, "future": {"x": true}\n}\n'
        enqueued_at = datetime(2026, 9, 16, 1, 2, 3, tzinfo=timezone.utc)
        kafka = self.spark.createDataFrame(
            [(body.encode("utf-8"), "evh-canopy-gps-dev", 2, 987654321, enqueued_at)],
            "value binary, topic string, partition int, offset long, timestamp timestamp",
        )

        row = bronze_rows(kafka).collect()[0]

        self.assertEqual(row.body, body)
        self.assertIn("1.2300", row.body)
        self.assertIn("서울", row.body)
        self.assertIn('"future"', row.body)
        self.assertEqual(row.event_hub_topic, "evh-canopy-gps-dev")
        self.assertEqual(row.event_hub_partition, 2)
        self.assertEqual(row.event_hub_offset, 987654321)
        self.assertEqual(row.event_hub_enqueued_at, enqueued_at.replace(tzinfo=None))
        self.assertIsNotNone(row.ingested_at)


if __name__ == "__main__":
    import unittest

    unittest.main()
