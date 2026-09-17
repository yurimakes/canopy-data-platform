import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cloud.azure.pipelines.gps_streaming.mock_detector import MockDetectorConfig
from cloud.azure.pipelines.gps_streaming.transform_with_state import (
    CanopyGpsStatefulProcessor,
    TransformWithStateConfig,
    decode_trip_state,
    encode_trip_state,
)

UTC = timezone.utc
START = datetime(2026, 9, 15, tzinfo=UTC)


class FakeValueState:
    def __init__(self) -> None:
        self.value = None

    def exists(self) -> bool:
        return self.value is not None

    def get(self):
        return self.value

    def update(self, value) -> None:
        self.value = value


class FakeHandle:
    def __init__(self) -> None:
        self.state = FakeValueState()
        self.request = None

    def getValueState(self, name, schema):
        self.request = (name, schema)
        return self.state


def row(sequence: int) -> SimpleNamespace:
    event_time = START + timedelta(seconds=sequence)
    return SimpleNamespace(
        schema_version="canopy.gps.collector.v0.1",
        event_id=f"event-{sequence}",
        user_id="user-1",
        device_id="device-1",
        trip_id="trip-1",
        sequence=sequence,
        event_time=event_time,
        received_at=event_time,
        lat=37.5 + sequence * 0.00001,
        lon=127.0,
        accuracy=5.0,
        raw_speed=None,
        altitude_m=None,
        vertical_accuracy=None,
    )


class TransformWithStateConfigTest(unittest.TestCase):
    def test_requires_a_durable_checkpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            TransformWithStateConfig(checkpoint_location=" ")


class TripStateCodecTest(unittest.TestCase):
    def test_json_round_trip_is_versioned_and_contains_no_pickle(self) -> None:
        encoded = encode_trip_state({"version": 1, "first_layer": {}})
        self.assertTrue(encoded.startswith("{"))
        self.assertEqual(decode_trip_state(encoded)["version"], 1)
        self.assertNotIn("pickle", encoded)

    def test_rejects_unknown_envelope_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "envelope version"):
            decode_trip_state('{"state_version":2,"runtime":{}}')


class CanopyGpsStatefulProcessorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.handle = FakeHandle()
        self.processor = CanopyGpsStatefulProcessor(
            MockDetectorConfig(min_speed_points=250, max_speed_points=250),
            row_factory=lambda **values: values,
            clock=lambda: START,
        )
        self.processor.init(self.handle)

    def test_registers_one_versioned_value_state(self) -> None:
        self.assertEqual(
            self.handle.request,
            ("canopy_trip_state", "state_json STRING NOT NULL"),
        )

    def test_restores_state_between_microbatches_and_sorts_each_batch(self) -> None:
        first = list(
            self.processor.handleInputRows(
                ("trip-1",), iter(row(i) for i in reversed(range(126)))
            )
        )
        restored = decode_trip_state(self.handle.state.value[0])
        detector_state = restored["first_layer"]["detector"]
        self.assertEqual(detector_state["target_points"], 250)
        self.assertEqual(detector_state["point_count"], 125)

        second = list(
            self.processor.handleInputRows(
                ("trip-1",), iter(row(i) for i in reversed(range(126, 251)))
            )
        )

        self.assertEqual(len(first), 126)
        self.assertEqual(first[0]["event_id"], "event-0")
        self.assertEqual(len(second), 126)
        self.assertEqual(second[-1]["record_type"], "segment")
        self.assertEqual(second[-1]["speed_point_count"], 250)
        self.assertEqual(second[-1]["segment_id"], "trip-1:mock:0001")
        self.assertIsNotNone(self.handle.state.value)

    def test_rejects_a_row_under_the_wrong_grouping_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "grouping key"):
            list(self.processor.handleInputRows(("other-trip",), iter([row(0)])))


try:
    from pyspark.sql import Row
    from pyspark.sql.streaming import TwsTester

    HAVE_TWS_TESTER = True
except ImportError:
    HAVE_TWS_TESTER = False


@unittest.skipUnless(HAVE_TWS_TESTER, "TwsTester requires Spark 4 / DBR 17.3")
class CanopyTwsTesterTest(unittest.TestCase):
    def test_processor_with_spark_tws_tester(self) -> None:
        processor = CanopyGpsStatefulProcessor(
            MockDetectorConfig(min_speed_points=250, max_speed_points=250)
        )
        tester = TwsTester(processor)
        result = tester.test(
            ("trip-1",),
            [Row(**vars(row(0))), Row(**vars(row(1)))],
        )
        self.assertEqual([item.record_type for item in result], ["feature", "feature"])
        self.assertIsNotNone(tester.peekValueState("canopy_trip_state", ("trip-1",)))


if __name__ == "__main__":
    unittest.main()
