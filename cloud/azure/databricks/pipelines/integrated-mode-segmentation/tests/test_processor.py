from __future__ import annotations

from datetime import datetime, timedelta, timezone

from integrated_mode_segmentation.processor import TripSegmentationProcessor
from integrated_mode_segmentation.state_machine import PredictionPoint, TripEnd, TripSegmentationState


BASE = datetime(2026, 9, 20, tzinfo=timezone.utc)


def prediction(sequence: int) -> PredictionPoint:
    return PredictionPoint(
        f"p{sequence}", "u1", "t1", sequence, BASE + timedelta(seconds=sequence),
        37.0, 127.0 + sequence / 10_000, "car", None, "m", "1", BASE,
    )


def completion(generation: int = 1) -> TripEnd:
    return TripEnd(f"e{generation}", "t1", "u1", 2, generation, BASE, "databricks")


def test_typed_state_round_trip_preserves_replay_and_generation_history() -> None:
    original = TripSegmentationState("t1", 3)
    original.accept_prediction(prediction(1))
    original.accept_prediction(prediction(2))
    original.accept_trip_end(completion())
    assert len(original.drain_outputs(BASE)) == 1

    restored = TripSegmentationState.from_state_dict(original.to_state_dict())
    restored.accept_prediction(prediction(1))
    assert not restored.conflicted
    restored.accept_trip_end(completion(2))
    rows = restored.drain_outputs(BASE)
    assert [row.segment_id for row in rows] == ["t1:g2:segment:1"]


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

    def getValueState(self, name, schema, ttlDurationMs):
        self.request = (name, schema, ttlDurationMs)
        return self.state


def union_row(event):
    if isinstance(event, PredictionPoint):
        values = event.as_dict()
        return {
            "event_kind": "prediction",
            **values,
            "expected_last_sequence": None,
            "processing_generation": None,
            "trip_end_parsed_at": None,
            "result_owner": None,
        }
    return {
        "event_kind": "trip_end",
        "event_id": event.event_id,
        "user_id": event.user_id,
        "trip_id": event.trip_id,
        "sequence": None,
        "event_time": None,
        "lat": None,
        "lon": None,
        "predicted_mode": None,
        "confidence": None,
        "model_name": None,
        "model_version": None,
        "predicted_at": None,
        "expected_last_sequence": event.expected_last_sequence,
        "processing_generation": event.processing_generation,
        "trip_end_parsed_at": event.parsed_at,
        "result_owner": event.result_owner,
    }


def test_processor_persists_typed_state_and_does_not_reemit_checkpoint_replay() -> None:
    handle = FakeHandle()
    processor = TripSegmentationProcessor(7_200_000, now=lambda: BASE, row_factory=lambda **v: v)
    processor.init(handle)

    first = list(
        processor.handleInputRows(
            ("t1",),
            iter([union_row(prediction(1)), union_row(prediction(2)), union_row(completion())]),
        )
    )
    assert [row["segment_id"] for row in first] == ["t1:g1:segment:1"]
    assert handle.request[2] == 7_200_000

    replay_processor = TripSegmentationProcessor(
        7_200_000, now=lambda: BASE, row_factory=lambda **v: v
    )
    replay_processor.init(handle)
    replay = list(
        replay_processor.handleInputRows(
            ("t1",),
            iter([union_row(prediction(1)), union_row(completion())]),
        )
    )
    assert replay == []
