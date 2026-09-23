import copy
import json

from tests.spark.support import SparkTestCase, load_fixture


class ObservationValidationTest(SparkTestCase):
    def assertValid(self, payload):
        row = self.parsed_payload(payload)
        self.assertEqual(row.rejection_reasons, [], row.rejection_reasons)
        self.assertIsNone(row.rejection_reason)
        return row

    def assertRejectedWith(self, payload, reason):
        row = self.parsed_payload(payload)
        self.assertIn(reason, row.rejection_reasons)
        return row

    def test_valid_v01_and_labels_are_preserved(self):
        row = self.assertValid(load_fixture("gps_v0_1_valid.json"))
        self.assertEqual(row.label, "walking")
        self.assertIsNone(row.collection_mode)

    def test_valid_v02_user_with_explicit_nulls(self):
        row = self.assertValid(load_fixture("gps_v0_2_user_valid.json"))
        self.assertIsNone(row.label)
        self.assertIsNone(row.raw_speed)

    def test_valid_v02_developer_and_unknown_fields(self):
        payload = load_fixture("gps_v0_2_developer_valid.json")
        payload["future_extension"] = {"kept": "in bronze"}
        row = self.assertValid(payload)
        self.assertEqual(row.label, "bike")

    def test_missing_nullable_key_is_not_explicit_null(self):
        payload = load_fixture("gps_v0_2_user_valid.json")
        del payload["speed"]
        row = self.assertRejectedWith(payload, "missing_required:speed")
        self.assertEqual(row.rejection_reason, "missing_required:speed")

    def test_malformed_and_wrong_top_level_json(self):
        self.assertEqual(self.parsed_payload("{bad").rejection_reason, "malformed_json")
        for body in ("42", "[1,2,3]", '"gps"', "null"):
            with self.subTest(body=body):
                self.assertEqual(
                    self.parsed_payload(body).rejection_reason,
                    "invalid_top_level_type",
                )

    def test_version_uuid_timestamp_and_sequence_validation(self):
        base = load_fixture("gps_v0_2_developer_valid.json")
        cases = (
            ("schema_version", "canopy.gps.collector.v9", "unsupported_schema_version"),
            ("event_id", "not-a-uuid", "invalid_uuid:event_id"),
            ("event_time", "2026-09-16T03:02:03+09:00", "invalid_timestamp:event_time"),
            ("sequence", 0, "invalid_sequence"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field):
                payload = copy.deepcopy(base)
                payload[field] = value
                self.assertRejectedWith(payload, reason)

    def test_numeric_ranges_and_source(self):
        base = load_fixture("gps_v0_2_developer_valid.json")
        cases = (
            ("lat", 91, "invalid_lat"),
            ("lon", -181, "invalid_lon"),
            ("accuracy", -0.1, "invalid_accuracy"),
            ("speed", -0.1, "invalid_speed"),
            ("vertical_accuracy_m", -0.1, "invalid_vertical_accuracy_m"),
            ("course_deg", 360, "invalid_course_deg"),
            ("source", "gps", "invalid_source"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field):
                payload = copy.deepcopy(base)
                payload[field] = value
                self.assertRejectedWith(payload, reason)

    def test_quality_flags_and_raw_location(self):
        base = load_fixture("gps_v0_2_developer_valid.json")
        cases = (
            ("quality_flags", "flag", "invalid_type:quality_flags"),
            ("quality_flags", ["same", "same"], "invalid_quality_flags"),
            ("quality_flags", ["ok", 1], "invalid_quality_flags"),
            ("raw_location", [], "invalid_raw_location"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field, value=value):
                payload = copy.deepcopy(base)
                payload[field] = value
                self.assertRejectedWith(payload, reason)

    def test_collection_mode_label_rules(self):
        base = load_fixture("gps_v0_2_developer_valid.json")
        cases = (
            ("automated", "bike", "invalid_collection_mode"),
            ("developer", "cycling", "invalid_label"),
            ("user", "walk", "incompatible_collection_mode_label"),
            ("developer", None, "incompatible_collection_mode_label"),
        )
        for mode, label, reason in cases:
            with self.subTest(mode=mode, label=label):
                payload = copy.deepcopy(base)
                payload["collection_mode"] = mode
                payload["label"] = label
                self.assertRejectedWith(payload, reason)

    def test_legacy_vertical_accuracy_alias_is_not_supported(self):
        payload = load_fixture("gps_v0_1_valid.json")
        payload["vertical_accuracy"] = payload.pop("vertical_accuracy_m")
        self.assertRejectedWith(payload, "missing_required:vertical_accuracy_m")

    def test_wrong_json_type_is_distinct_from_invalid_value(self):
        payload = load_fixture("gps_v0_2_developer_valid.json")
        payload["speed"] = "4.75"
        row = self.assertRejectedWith(payload, "invalid_type:speed")
        self.assertNotIn("invalid_speed", row.rejection_reasons)

    def test_all_reasons_are_retained_with_deterministic_primary(self):
        payload = load_fixture("gps_v0_2_developer_valid.json")
        payload["event_id"] = "bad"
        payload["lat"] = 100
        payload["speed"] = -1
        row = self.parsed_payload(payload)
        self.assertEqual(row.rejection_reason, "invalid_uuid:event_id")
        self.assertIn("invalid_lat", row.rejection_reasons)
        self.assertIn("invalid_speed", row.rejection_reasons)


if __name__ == "__main__":
    import unittest

    unittest.main()
