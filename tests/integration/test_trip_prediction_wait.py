"""Final Segment 경계, 종료정보 대조, 제한시간과 후속 탄소 계산 검증."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud/azure/pipelines/databricks"))
from trip_prediction_wait import resolve, advance, normalize_table_result
from finalize_trip_pipeline import build_final_trip
from services.trip_processor import ProcessingError


def sample():
    return {"trip": {"trip_id": "trip_001", "user_id": "user_001", "campaign_id": "campaign_test",
        "started_at": "2026-09-17T09:00:00+09:00", "ended_at": "2026-09-17T09:20:00+09:00",
        "processing_generation": 1}, "result": {"trip_id": "trip_001", "model_version": "canopy-mode-v1",
        "segments": [{"segment_id": "trip_001:segment:1", "mode": "walk",
            "start_time": "2026-09-17T09:00:00+09:00", "end_time": "2026-09-17T09:05:00+09:00",
            "distance_m": 350.0, "confidence": 0.92},
            {"segment_id": "trip_001:segment:2", "mode": "bus",
            "start_time": "2026-09-17T09:05:00+09:00", "end_time": "2026-09-17T09:20:00+09:00",
            "distance_m": 5200.0, "confidence": None}]}, "completed_at": "2026-09-17T09:20:10+09:00"}


class FinalSegmentTests(unittest.TestCase):
    def setUp(self):
        self.value = sample()
        self.end = {**self.value["trip"], "result_owner": "databricks", "expected_last_sequence": 120}

    def test_agreed_schema_to_carbon_preserves_null_distance_and_completion(self):
        import jsonschema
        schema = json.loads((ROOT / "shared/schemas/final_segment.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(self.value)
        reason, payload = resolve(self.end, [self.value])
        self.assertEqual(reason, "ready")
        doc = build_final_trip(json.loads(payload))
        self.assertEqual(doc["confirmed_trip"]["total_distance_m"], 5550)
        self.assertEqual(doc["segments"][1]["confidence"], None)
        self.assertEqual(doc["updated_at"], self.value["completed_at"])
        self.value["result"]["segments"][1]["confidence"] = 0
        other = build_final_trip(self.value)
        self.assertEqual(doc["carbon"], other["carbon"])
        self.assertEqual(other["segments"][1]["confidence"], 0)
        self.assertFalse(doc["is_mock"])

    def test_team_table_extra_columns_and_duplicate_identity(self):
        row = copy.deepcopy(self.value)
        row.update(trip_id=row["trip"]["trip_id"], processing_generation=1, model_name="team")
        row["trip"]["status"] = "completed"
        row["result"]["segments"][0].update(segment_index=1, start_sequence=1, end_sequence=12)
        self.assertEqual(normalize_table_result(row), self.value)
        row["result"]["segments"][0]["mode"] = "subway"
        self.assertEqual(normalize_table_result(row)["result"]["segments"][0]["mode"], "rail")
        self.assertEqual(row["result"]["segments"][0]["mode"], "subway")
        row["processing_generation"] = 2
        with self.assertRaises(ValueError):
            normalize_table_result(row)

    def test_other_user_and_generations_never_satisfy_end(self):
        for key, value in [("user_id", "other"), ("trip_id", "other"), ("processing_generation", 2)]:
            wrong = copy.deepcopy(self.value)
            wrong["trip"][key] = value
            self.assertEqual(resolve(self.end, [wrong]), ("waiting_for_final_segments", None))

    def test_duplicates_and_conflicting_completed_results(self):
        self.assertEqual(resolve(self.end, [self.value]*2)[0], "ready")
        wrong = copy.deepcopy(self.value)
        wrong["result"]["segments"][1]["distance_m"] += 10
        self.assertEqual(resolve(self.end, [self.value, wrong]), ("conflicting_final_segments", None))

    def test_lifecycle_mismatch_and_equivalent_timezone(self):
        wrong = copy.deepcopy(self.value)
        wrong["trip"]["campaign_id"] = "other"
        self.assertEqual(resolve(self.end, [wrong])[0], "lifecycle_context_mismatch")
        self.end["ended_at"] = "2026-09-17T00:20:00+00:00"
        self.assertEqual(resolve(self.end, [self.value])[0], "ready")

    def test_timeout_and_bounded_attempts(self):
        now = datetime.now(timezone.utc)
        wait = {"attempts": 0, "deadline_at": now+timedelta(seconds=600)}
        first = advance(wait, "waiting_for_final_segments", None, now)
        self.assertEqual(first["status"], "waiting")
        self.assertEqual(first["next_check_at"], now+timedelta(seconds=10))
        self.assertEqual(advance(wait, "ready", "{}", now+timedelta(seconds=601))["status"], "timed_out")
        self.assertEqual(advance({**wait,"attempts":11}, "waiting_for_final_segments", None, now)["status"], "timed_out")
        self.assertEqual(advance(wait,"conflicting_final_segments",None,now)["status"],"failed")

    def test_invalid_completed_contract_never_becomes_final_trip(self):
        mutations = [lambda v:v.update(provider="external"),
            lambda v:v["trip"].update(status="processing"),
            lambda v:v.update(completed_at="2026-09-17T08:00:00+09:00"),
            lambda v:v["result"].update(trip_id="other"),
            lambda v:v["result"]["segments"][0].update(distance_m=-1),
            lambda v:v["result"]["segments"][0].update(confidence=1.1),
            lambda v:v["result"]["segments"][0].update(confidence=float("nan")),
            lambda v:v["result"]["segments"][0].pop("confidence"),
            lambda v:v["result"].update(model_version="mock_v1")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = sample()
                mutation(value)
                with self.assertRaises((ValueError, ProcessingError)):
                    build_final_trip(value)


if __name__ == "__main__":
    unittest.main()
