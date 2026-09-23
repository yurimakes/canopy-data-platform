import unittest

from gps_ingestion.spark_ingestion import deduplicate_observations


class _Frame:
    def __init__(self) -> None:
        self.calls = []

    def withWatermark(self, column, horizon):
        self.calls.append(("withWatermark", column, horizon))
        return self

    def dropDuplicatesWithinWatermark(self, keys):
        self.calls.append(("dropDuplicatesWithinWatermark", keys))
        return self


class DeduplicationContractTest(unittest.TestCase):
    def test_uses_enqueue_time_and_event_id(self) -> None:
        frame = _Frame()
        self.assertIs(deduplicate_observations(frame, " 2 days "), frame)
        self.assertEqual(
            frame.calls,
            [
                ("withWatermark", "event_hub_enqueued_at", "2 days"),
                ("dropDuplicatesWithinWatermark", ["event_id"]),
            ],
        )

    def test_requires_a_watermark(self) -> None:
        with self.assertRaisesRegex(ValueError, "watermark is required"):
            deduplicate_observations(_Frame(), " ")


if __name__ == "__main__":
    unittest.main()
