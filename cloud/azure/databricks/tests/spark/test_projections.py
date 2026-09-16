import json

from gps_ingestion.spark_ingestion import (
    parse_bronze_rows,
    quarantine_rows,
    valid_observation_rows,
)
from tests.spark.support import SparkTestCase, load_fixture


class ProjectionTest(SparkTestCase):
    def test_observation_projection_renames_speed_without_changing_value(self):
        payload = load_fixture("gps_v0_2_developer_valid.json")
        payload["future_extension"] = {"unknown": True}
        body = json.dumps(payload, ensure_ascii=False)

        observations = valid_observation_rows(
            parse_bronze_rows(self.bronze_frame([body]))
        )
        row = observations.collect()[0]

        self.assertEqual(row.raw_speed, payload["speed"])
        self.assertNotIn("speed", observations.columns)
        self.assertNotIn("raw_location", observations.columns)
        self.assertNotIn("future_extension", observations.columns)
        self.assertEqual(row.event_hub_topic, "evh-canopy-gps-dev")
        self.assertEqual(row.event_hub_partition, 3)
        self.assertEqual(row.event_hub_offset, 101)
        self.assertIsNotNone(row.event_hub_enqueued_at)

    def test_quarantine_retains_body_all_reasons_and_provenance(self):
        payload = load_fixture("gps_v0_2_developer_valid.json")
        payload["event_id"] = "bad"
        payload["lat"] = 100
        body = json.dumps(payload, ensure_ascii=False, indent=2)

        row = quarantine_rows(
            parse_bronze_rows(self.bronze_frame([body]))
        ).collect()[0]

        self.assertEqual(row.body, body)
        self.assertEqual(row.event_id, "bad")
        self.assertEqual(row.rejection_reason, "invalid_uuid:event_id")
        self.assertIn("invalid_lat", row.rejection_reasons)
        self.assertEqual(row.event_hub_topic, "evh-canopy-gps-dev")
        self.assertEqual(row.event_hub_partition, 3)
        self.assertEqual(row.event_hub_offset, 101)
        self.assertIn('"raw_location"', row.body)

    def test_valid_duplicates_remain_in_bronze_and_are_not_quarantined(self):
        payload = load_fixture("gps_v0_2_developer_valid.json")
        body = json.dumps(payload)
        bronze = self.bronze_frame([body, body])
        parsed = parse_bronze_rows(bronze)

        self.assertEqual(bronze.count(), 2)
        self.assertEqual(valid_observation_rows(parsed).count(), 2)
        self.assertEqual(quarantine_rows(parsed).count(), 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
