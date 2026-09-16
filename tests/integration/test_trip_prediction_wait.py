"""Real Spark joins against the current ML column contract; no Azure writes."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud/azure/pipelines/databricks"))
from trip_prediction_wait import assess, advance
from finalize_trip_pipeline import build_final_trip


class PredictionWaitTests(unittest.TestCase):
    def test_coverage_timeout_and_existing_carbon(self):
        from pyspark.sql import SparkSession, functions as F
        spark = SparkSession.builder.master("local[2]").appName("trip-prediction-wait-test").config(
            "spark.sql.shuffle.partitions", "2").config("spark.ui.enabled", "false").getOrCreate()
        spark.conf.set("spark.sql.session.timeZone", "UTC")
        now = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
        at = lambda seconds: now + timedelta(seconds=seconds)
        try:
            end_schema = "user_id string, trip_id string, processing_generation long, campaign_id string, started_at timestamp, ended_at timestamp, expected_last_sequence long, result_owner string, attempts int, deadline_at timestamp"
            ends = spark.createDataFrame([(u, "trip", 1, "campaign", at(0), at(10), 4, "databricks", 0, at(600))
                                           for u in ("ready", "tail", "gap", "unscored")], end_schema)
            gps_schema = "user_id string, trip_id string, event_id string, sequence long, event_time timestamp, distance_m double, transition_valid boolean"
            gps = spark.createDataFrame([(u, "trip", u+str(i), i, at(i), 0.0 if i==1 else 10.0, i>1)
                  for u in ("ready", "tail", "gap", "unscored") for i in range(1,5) if not(u=="gap" and i==3)], gps_schema)
            ps = "user_id string, trip_id string, segment_id string, start_time timestamp, end_time timestamp, strong_mode string, strong_confidence double, inference_status string, model_uri string"
            preds = spark.createDataFrame([(u,"trip",u+"s1",at(2),at(3),"walk",0.9,"scored","models:/team/1")
                for u in ("ready","tail","gap","unscored")] +
                [(u,"trip",u+"s2",at(3),at(4),"train",0.8,"insufficient_history" if u=="unscored" else "scored","models:/team/1")
                for u in ("ready","gap","unscored")], ps)
            checks = advance(assess(ends,gps,preds),at(15)).cache()
            values = {r.user_id:r for r in checks.collect()}
            self.assertEqual(values['ready'].status,'ready')
            self.assertEqual(values['tail'].reason,'waiting_for_prediction_coverage')
            self.assertEqual(values['gap'].reason,'waiting_for_gps')
            self.assertEqual(values['unscored'].reason,'waiting_for_scored_predictions')
            self.assertEqual(values['tail'].status,'waiting')
            self.assertEqual(values['tail'].attempts,1)
            envelope=json.loads(values['ready'].envelope_json)
            self.assertEqual(sum(x['distance_m'] for x in envelope['result']['segments']),30)
            self.assertEqual(envelope['result']['segments'][1]['mode'],'rail')
            document=build_final_trip(envelope)
            self.assertEqual(document['status'],'ready')
            self.assertEqual(document['confirmed_trip']['total_distance_m'],30)
            # Once the ten-minute budget is over, even newly available data needs explicit retry.
            expired=advance(checks.drop('status','next_check_at','checked_at','envelope_json'),at(601)).collect()
            self.assertTrue(all(r.status=='timed_out' and r.envelope_json is None for r in expired))
            # Two owners with the same Trip ID never share predictions or GPS coverage.
            self.assertNotEqual(values['ready'].status,values['tail'].status)
            checks.unpersist()
        finally:
            spark.stop()


if __name__ == '__main__':
    unittest.main()
