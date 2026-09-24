from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mode_detection.spark_processor as spark_processor
from mode_detection.contract import ModeModelMetadata, ModePrediction


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeValueState:
    def __init__(self):
        self.value = None

    def exists(self):
        return self.value is not None

    def get(self):
        return self.value

    def update(self, value):
        self.value = value


class FakeHandle:
    def __init__(self, state):
        self.state = state

    def getValueState(self, _name, _schema, ttlDurationMs=None):
        assert ttlDurationMs == 7200000
        return self.state


class FakeModel:
    def __init__(self):
        self._metadata = ModeModelMetadata(
            "fake-hgbc",
            "test-v1",
            "feature-v1",
            120,
            10,
        )

    @property
    def metadata(self):
        return self._metadata

    def prediction_ready(self, observations, *, window_end):
        start = window_end - timedelta(seconds=120)
        points = [p for p in observations if start <= p.event_time <= window_end]
        return (
            len(points) >= 2
            and points[0].event_time <= start
            and points[-1].event_time >= window_end
        )

    def predict(self, observations, *, window_end, raw_point_count):
        return ModePrediction(
            predicted_mode="bus",
            confidence=0.8,
            probabilities={"bus": 0.8, "walk": 0.2},
            window_start=window_end - timedelta(seconds=120),
            window_end=window_end,
            metadata=self.metadata,
        )


def resolver(probabilities, _observations, _station_history):
    return (
        {
            "final_mode": "bus",
            "decision_confidence": probabilities["bus"],
            "decision_status": "unchanged",
            "correction_applied": False,
            "correction_reason": "ML prediction retained",
        },
        {},
    )


def gps_row(sequence: int, seconds: int):
    return {
        "event_kind": "gps",
        "event_id": f"gps-{sequence}",
        "trip_id": "trip-1",
        "user_id": "user-1",
        "sequence": sequence,
        "event_time": BASE + timedelta(seconds=seconds),
        "lat": 37.0,
        "lon": 127.0 + sequence * 0.00001,
        "accuracy": 5.0,
        "altitude_m": 10.0,
        "campaign_id": None,
        "started_at": None,
        "ended_at": None,
        "expected_last_sequence": None,
        "occurred_at": None,
        "processing_generation": None,
        "result_owner": None,
    }


def trip_end_row(*, ended_seconds: int = 123, expected_last_sequence: int = 124):
    return {
        "event_kind": "trip_end",
        "event_id": "trip-end-1",
        "trip_id": "trip-1",
        "user_id": "user-1",
        "sequence": None,
        "event_time": None,
        "lat": None,
        "lon": None,
        "accuracy": None,
        "altitude_m": None,
        "campaign_id": "campaign-1",
        "started_at": BASE,
        "ended_at": BASE + timedelta(seconds=ended_seconds),
        "expected_last_sequence": expected_last_sequence,
        "occurred_at": BASE + timedelta(seconds=ended_seconds),
        "processing_generation": 1,
        "result_owner": "mode-detection",
    }


def test_stateful_processor_emits_sealed_result(monkeypatch):
    monkeypatch.setattr(
        spark_processor,
        "_runtime",
        lambda *_args: (FakeModel(), resolver),
    )

    monkeypatch.setattr(
        spark_processor,
        "build_complete_payload",
        lambda sealed, distances, **kwargs: {
            "trip_id": sealed.trip_end.trip_id,
            "user_id": sealed.trip_end.user_id,
            "campaign_id": sealed.trip_end.campaign_id,
            "status": "ready",
            "started_at": BASE.isoformat(),
            "ended_at": (BASE + timedelta(seconds=123)).isoformat(),
            "updated_at": (BASE + timedelta(seconds=124)).isoformat(),
            "processing_generation": 1,
            "expected_last_sequence": 124,
            "segments": [
                {
                    "segment_id": "trip-1:segment:1",
                    "mode": "bus",
                    "model_prediction": "bus",
                    "start_time": BASE.isoformat(),
                    "end_time": (BASE + timedelta(seconds=123)).isoformat(),
                    "distance_m": 1.0,
                    "confidence": 0.8,
                    "prediction_count": 1,
                    "carbon_kg": 0.0,
                }
            ],
            "model_name": "fake-hgbc",
            "model_version": "test-v1",
            "feature_version": "feature-v1",
            "total_distance_m": 1.0,
            "carbon": {
                "kg_co2e": 0.0,
                "policy_version": "test",
                "factor_version": "test",
                "unit": "kgCO2e",
                "mode_source": "model_prediction",
                "user_confirmation_applied": False,
            },
            "finalization_hash": "hash",
            "document_json": "{}",
        },
    )

    value_state = FakeValueState()
    processor = spark_processor.ModeDetectionStatefulProcessor(
        ttl_duration_ms=7200000,
        artifact_path="/unused/model.joblib",
        prediction_stride_seconds=10,
        reference_root="/unused/reference",
        transit_reference_dir="/unused/transit",
        carbon_policy_path="/unused/carbon_policy.yaml",
        now=lambda: BASE + timedelta(seconds=124),
        row_factory=lambda **values: values,
    )
    processor.init(FakeHandle(value_state))

    rows = [
        gps_row(index + 1, seconds)
        for index, seconds in enumerate(range(0, 124))
    ]
    rows.append(trip_end_row())

    outputs = list(processor.handleInputRows(("trip-1",), iter(rows)))

    assert len(outputs) == 1
    output = outputs[0]
    assert output["trip_id"] == "trip-1"
    assert output["processing_generation"] == 1
    assert output["segments"][0]["mode"] == "bus"
    assert output["segments"][0]["start_time"] == BASE.isoformat()
    assert output["segments"][0]["end_time"] == (BASE + timedelta(seconds=123)).isoformat()
    assert output["status"] == "ready"
    assert output["finalization_hash"] == "hash"
    assert value_state.exists()


def test_replaying_same_state_does_not_reemit_generation(monkeypatch):
    monkeypatch.setattr(
        spark_processor,
        "_runtime",
        lambda *_args: (FakeModel(), resolver),
    )

    monkeypatch.setattr(
        spark_processor,
        "build_complete_payload",
        lambda sealed, distances, **kwargs: {
            "trip_id": sealed.trip_end.trip_id,
            "user_id": sealed.trip_end.user_id,
            "campaign_id": sealed.trip_end.campaign_id,
            "status": "ready",
            "started_at": BASE.isoformat(),
            "ended_at": (BASE + timedelta(seconds=123)).isoformat(),
            "updated_at": (BASE + timedelta(seconds=124)).isoformat(),
            "processing_generation": 1,
            "expected_last_sequence": 124,
            "segments": [
                {
                    "segment_id": "trip-1:segment:1",
                    "mode": "bus",
                    "model_prediction": "bus",
                    "start_time": BASE.isoformat(),
                    "end_time": (BASE + timedelta(seconds=123)).isoformat(),
                    "distance_m": 1.0,
                    "confidence": 0.8,
                    "prediction_count": 1,
                    "carbon_kg": 0.0,
                }
            ],
            "model_name": "fake-hgbc",
            "model_version": "test-v1",
            "feature_version": "feature-v1",
            "total_distance_m": 1.0,
            "carbon": {
                "kg_co2e": 0.0,
                "policy_version": "test",
                "factor_version": "test",
                "unit": "kgCO2e",
                "mode_source": "model_prediction",
                "user_confirmation_applied": False,
            },
            "finalization_hash": "hash",
            "document_json": "{}",
        },
    )

    value_state = FakeValueState()
    processor = spark_processor.ModeDetectionStatefulProcessor(
        ttl_duration_ms=7200000,
        artifact_path="/unused/model.joblib",
        prediction_stride_seconds=10,
        reference_root="/unused/reference",
        transit_reference_dir="/unused/transit",
        carbon_policy_path="/unused/carbon_policy.yaml",
        row_factory=lambda **values: values,
    )
    processor.init(FakeHandle(value_state))

    first_rows = [
        gps_row(index + 1, seconds)
        for index, seconds in enumerate(range(0, 124))
    ]
    first_rows.append(trip_end_row())
    assert len(list(processor.handleInputRows(("trip-1",), iter(first_rows)))) == 1

    assert list(
        processor.handleInputRows(
            ("trip-1",),
            iter([trip_end_row()]),
        )
    ) == []


def test_short_trip_emits_terminal_payload_instead_of_raising(monkeypatch):
    monkeypatch.setattr(
        spark_processor,
        "_runtime",
        lambda *_args: (FakeModel(), resolver),
    )

    def fake_payload(sealed, distances, **kwargs):
        del distances, kwargs
        return {
            "trip_id": sealed.trip_end.trip_id,
            "user_id": sealed.trip_end.user_id,
            "campaign_id": sealed.trip_end.campaign_id,
            "status": sealed.status,
            "mode_detection_reason": sealed.reason,
            "started_at": BASE.isoformat(),
            "ended_at": (BASE + timedelta(seconds=60)).isoformat(),
            "updated_at": (BASE + timedelta(seconds=61)).isoformat(),
            "processing_generation": 1,
            "expected_last_sequence": 61,
            "segments": [],
            "model_name": "fake-hgbc",
            "model_version": "test-v1",
            "feature_version": "feature-v1",
            "total_distance_m": 0.0,
            "carbon": {
                "kg_co2e": 0.0,
                "policy_version": "test",
                "factor_version": "test",
                "unit": "kgCO2e",
                "mode_source": "unavailable",
                "user_confirmation_applied": False,
            },
            "finalization_hash": "short-hash",
            "document_json": "{}",
        }

    monkeypatch.setattr(spark_processor, "build_complete_payload", fake_payload)

    value_state = FakeValueState()
    processor = spark_processor.ModeDetectionStatefulProcessor(
        ttl_duration_ms=7200000,
        artifact_path="/unused/model.joblib",
        prediction_stride_seconds=10,
        reference_root="/unused/reference",
        transit_reference_dir="/unused/transit",
        carbon_policy_path="/unused/carbon_policy.yaml",
        now=lambda: BASE + timedelta(seconds=61),
        row_factory=lambda **values: values,
    )
    processor.init(FakeHandle(value_state))

    rows = [gps_row(i + 1, i) for i in range(61)]
    rows.append(trip_end_row(ended_seconds=60, expected_last_sequence=61))

    outputs = list(processor.handleInputRows(("trip-1",), iter(rows)))

    assert len(outputs) == 1
    assert outputs[0]["status"] == "insufficient_data"
    assert outputs[0]["mode_detection_reason"] == "trip_shorter_than_model_window"
    assert outputs[0]["segments"] == []
