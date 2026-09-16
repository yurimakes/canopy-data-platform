import tempfile
import uuid
from datetime import datetime, timezone

from gps_ingestion.spark_ingestion import deduplicate_observations
from tests.spark.support import SparkTestCase


class ObservationDeduplicationTest(SparkTestCase):
    def _run_dedup(self, rows):
        schema = "event_id string, event_time timestamp, event_hub_enqueued_at timestamp"
        with tempfile.TemporaryDirectory(prefix="canopy-dedup-") as directory:
            source = f"{directory}/source"
            checkpoint = f"{directory}/checkpoint"
            static = self.spark.createDataFrame(rows, schema)
            static.write.mode("overwrite").parquet(source)
            stream = self.spark.readStream.schema(static.schema).parquet(source)
            deduped = deduplicate_observations(stream, "1 day")
            query_name = f"gps_dedup_{uuid.uuid4().hex}"
            query = (
                deduped.writeStream.format("memory")
                .queryName(query_name)
                .option("checkpointLocation", checkpoint)
                .outputMode("append")
                .trigger(availableNow=True)
                .start()
            )
            query.awaitTermination()
            return self.spark.table(query_name).collect()

    def test_same_event_id_within_horizon_is_one_observation(self):
        old_event_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent_enqueue = datetime(2026, 9, 16, 4, 0, tzinfo=timezone.utc)
        rows = [
            ("same", old_event_time, recent_enqueue),
            ("same", old_event_time, recent_enqueue),
        ]
        self.assertEqual(len(self._run_dedup(rows)), 1)

    def test_different_event_ids_are_both_retained(self):
        old_event_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent_enqueue = datetime(2026, 9, 16, 4, 0, tzinfo=timezone.utc)
        rows = [
            ("first", old_event_time, recent_enqueue),
            ("second", old_event_time, recent_enqueue),
        ]
        output = self._run_dedup(rows)
        self.assertEqual({row.event_id for row in output}, {"first", "second"})


if __name__ == "__main__":
    import unittest

    unittest.main()
