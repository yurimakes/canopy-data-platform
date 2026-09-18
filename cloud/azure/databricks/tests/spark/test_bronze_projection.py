import json
from datetime import datetime, timezone

from gps_ingestion.event_ingestion import generic_bronze_rows
from tests.spark.support import SparkTestCase


class BronzeProjectionTest(SparkTestCase):
    def kafka_frame(self, bodies):
        enqueued_at = datetime(2026, 9, 18, 1, 2, 3, tzinfo=timezone.utc)
        return self.spark.createDataFrame(
            [
                (body.encode("utf-8"), "evh-canopy-gps-dev", 2, 987654321 + i, enqueued_at)
                for i, body in enumerate(bodies)
            ],
            "value binary, topic string, partition int, offset long, timestamp timestamp",
        )

    def test_raw_payload_and_event_hubs_coordinates_are_preserved(self):
        body = '{\n  "event_id": "11111111-1111-1111-1111-111111111111", "schema_version": "canopy.gps.collector.v0.2", "number": 1.2300, "memo": "서울"\n}\n'
        row = generic_bronze_rows(self.kafka_frame([body])).collect()[0]

        self.assertEqual(row.raw_payload, body)
        self.assertIn("1.2300", row.raw_payload)
        self.assertIn("서울", row.raw_payload)
        self.assertEqual(row.event_id, "11111111-1111-1111-1111-111111111111")
        self.assertIsNone(row.event_type)
        self.assertEqual(row.schema_version, "canopy.gps.collector.v0.2")
        self.assertEqual(row.event_hub_partition, 2)
        self.assertEqual(row.event_hub_offset, 987654321)
        self.assertIsNotNone(row.event_hub_enqueued_at)
        self.assertIsNotNone(row.ingested_at)

    def test_trip_ended_routing_metadata_is_extracted(self):
        payload = {
            "event_id": "22222222-2222-2222-2222-222222222222",
            "event_type": "trip_ended",
            "schema_version": "trip-lifecycle-v1",
            "trip_id": "trip-1",
        }
        row = generic_bronze_rows(
            self.kafka_frame([json.dumps(payload)])
        ).collect()[0]

        self.assertEqual(row.event_id, payload["event_id"])
        self.assertEqual(row.event_type, "trip_ended")
        self.assertEqual(row.schema_version, "trip-lifecycle-v1")

    def test_malformed_payload_remains_in_bronze(self):
        body = '{"event_id":'
        row = generic_bronze_rows(self.kafka_frame([body])).collect()[0]

        self.assertEqual(row.raw_payload, body)
        self.assertIsNone(row.event_id)
        self.assertIsNone(row.event_type)
        self.assertIsNone(row.schema_version)


if __name__ == "__main__":
    import unittest

    unittest.main()
