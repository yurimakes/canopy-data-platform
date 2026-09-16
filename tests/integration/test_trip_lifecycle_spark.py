"""Run with a full JDK and local PySpark; no Azure writes."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud/azure/pipelines"))
from gps_streaming.trip_lifecycle import parse_end_events, finalization_status, ML_COMPLETION_SCHEMA


class LifecycleSparkTests(unittest.TestCase):
    def test_interleaved_gps_end_duplicate_gap_and_ml_barrier(self):
        from pyspark.sql import SparkSession, functions as F
        spark = SparkSession.builder.master("local[2]").appName("trip-lifecycle-test").config(
            "spark.sql.shuffle.partitions", "2").config("spark.ui.enabled", "false").getOrCreate()
        try:
            def end(user):
                return {"event_id": "end-" + user, "event_type": "trip_ended", "schema_version": "trip-lifecycle-v1",
                        "trip_id": user + "-trip", "user_id": user, "campaign_id": "test",
                        "started_at": "2026-09-16T00:00:00Z", "ended_at": "2026-09-16T00:10:00Z",
                        "occurred_at": "2026-09-16T00:10:01Z", "processing_generation": 1,
                        "expected_last_sequence": 100, "result_owner": "databricks"}
            events = [end("A"), end("A"), end("C"), end("D")]
            events += [{"user_id": user, "trip_id": user + "-trip", "event_id": f"{user}-{seq}", "sequence": seq}
                       for user in ("A", "B", "C", "D") for seq in range(1,101) if user != "A" or seq not in (98,99)]
            bronze = spark.createDataFrame([(json.dumps(e),) for e in events], "body string").withColumn(
                "ingested_at", F.current_timestamp()).withColumn("event_hub_enqueued_at", F.current_timestamp()).cache()
            ends = parse_end_events(bronze).where("valid").cache()
            self.assertEqual(ends.count(), 4)
            ml = spark.createDataFrame([("A","A-trip",1,100,100,True,"ml_v1"),
                                        ("C","C-trip",1,97,97,False,"ml_v1"),
                                        ("D","D-trip",1,100,100,True,"ml_v1")], ML_COMPLETION_SCHEMA)
            states = {r.user_id: r for r in finalization_status(ends, bronze, ml).collect()}
            self.assertEqual(set(states), {"A", "C", "D"})
            self.assertFalse(states["A"].can_finalize)  # max is 100 but 98 and 99 are missing
            self.assertEqual(states["A"].end_variants, 1)  # retransmitted end did not create a second Trip
            self.assertEqual(states["C"].finalization_status, "waiting_for_segments")
            self.assertTrue(states["D"].can_finalize)
            added = spark.createDataFrame([(json.dumps({"user_id":"A","trip_id":"A-trip","event_id":f"A-{seq}","sequence":seq}),)
                                           for seq in (98,99)], "body string").withColumn("ingested_at",F.current_timestamp()).withColumn("event_hub_enqueued_at",F.current_timestamp())
            done = finalization_status(ends, bronze.unionByName(added), ml).where("user_id='A'").first()
            self.assertTrue(done.can_finalize)
            empty = spark.createDataFrame([], ML_COMPLETION_SCHEMA)
            self.assertFalse(finalization_status(ends, bronze, empty).where("user_id='D'").first().can_finalize)
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main()
