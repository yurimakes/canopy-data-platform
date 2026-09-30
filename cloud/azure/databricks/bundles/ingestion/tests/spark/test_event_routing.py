import json

from gps_ingestion.event_ingestion import gps_parser_input_rows, trip_ended_rows
from tests.spark.support import SparkTestCase, load_fixture


class EventRoutingTest(SparkTestCase):
    def test_gps_and_trip_ended_route_to_different_primitive_silver_paths(self):
        gps_body = json.dumps(load_fixture("gps_v0_2_developer_valid.json"))
        trip_body = json.dumps(
            {
                "event_id": "33333333-3333-3333-3333-333333333333",
                "event_type": "trip_ended",
                "schema_version": "trip-lifecycle-v1",
                "trip_id": "trip-1",
                "user_id": "user-1",
                "campaign_id": "campaign-1",
                "started_at": "2026-09-18T01:00:00Z",
                "ended_at": "2026-09-18T01:30:00Z",
                "expected_last_sequence": 1800,
                "occurred_at": "2026-09-18T01:30:01Z",
                "processing_generation": 1,
                "result_owner": "databricks",
            }
        )
        unknown_body = json.dumps(
            {
                "event_id": "44444444-4444-4444-4444-444444444444",
                "event_type": "future_event",
                "schema_version": "future-v1",
            }
        )

        bronze = self.generic_bronze_frame([gps_body, trip_body, unknown_body])

        gps = gps_parser_input_rows(bronze)
        trip = trip_ended_rows(bronze)

        self.assertEqual(gps.count(), 1)
        self.assertEqual(gps.collect()[0].body, gps_body)

        self.assertEqual(trip.count(), 1)
        row = trip.collect()[0]
        self.assertEqual(row.event_type, "trip_ended")
        self.assertEqual(row.schema_version, "trip-lifecycle-v1")
        self.assertEqual(row.expected_last_sequence, 1800)
        self.assertEqual(row.processing_generation, 1)
        self.assertEqual(row.result_owner, "databricks")
        self.assertIsNotNone(row.started_at)
        self.assertIsNotNone(row.ended_at)
        self.assertIsNotNone(row.occurred_at)
        self.assertIsNotNone(row.bronze_ingested_at)
        self.assertIsNotNone(row.parsed_at)

    def test_invalid_trip_ended_is_not_promoted_to_silver(self):
        payload = {
            "event_id": "not-a-uuid",
            "event_type": "trip_ended",
            "schema_version": "trip-lifecycle-v1",
            "trip_id": "trip-1",
            "user_id": "user-1",
            "campaign_id": "campaign-1",
            "started_at": "2026-09-18T01:00:00Z",
            "ended_at": "bad",
            "expected_last_sequence": -1,
            "occurred_at": "2026-09-18T01:30:01Z",
            "processing_generation": 0,
            "result_owner": "databricks",
        }
        bronze = self.generic_bronze_frame([json.dumps(payload)])
        self.assertEqual(trip_ended_rows(bronze).count(), 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
