"""Prepare deterministic GPS/prediction inputs, then emit trip_ended for segment-only latency tests."""
from __future__ import annotations
import argparse, time, uuid
from datetime import datetime, timezone
from pyspark.sql import SparkSession

def parse_args():
    p=argparse.ArgumentParser()
    for name in ("catalog","schema","source-table","gps-table","prediction-table","trip-ended-table","source-trip-id","run-id"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--users", type=int, default=5)
    p.add_argument("--points-per-user", type=int, default=300)
    p.add_argument("--sequences-per-batch", type=int, default=50)
    p.add_argument("--batch-interval-ms", type=int, default=0)
    return p.parse_args()

def now_utc_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def mode_for_sequence(sequence):
    modes=[(2,"car"),(0,"walk"),(3,"bus"),(0,"walk")]
    return modes[min((sequence-1)//75, 3)]

def main():
    a=parse_args()
    spark=SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    source_name=f"{a.catalog}.{a.schema}.{a.source_table}"
    gps_name=f"{a.catalog}.{a.schema}.{a.gps_table}"
    pred_name=f"{a.catalog}.{a.schema}.{a.prediction_table}"
    end_name=f"{a.catalog}.{a.schema}.{a.trip_ended_table}"

    source_df=(spark.table(source_name).where(f"trip_id = '{a.source_trip_id}'")
               .orderBy("sequence").limit(a.points_per_user))
    source_rows=source_df.collect()
    if len(source_rows)!=a.points_per_user:
        raise ValueError(f"requested {a.points_per_user} points but found {len(source_rows)}")

    gps_schema=spark.table(gps_name).schema
    pred_schema=spark.table(pred_name).schema
    identities=[]; gps_users=[]; pred_users=[]
    for u in range(a.users):
        user_id=f"segment-only:{a.run_id}:user:{u:02d}"
        trip_id=f"segment-only:{a.run_id}:trip:{u:02d}"
        identities.append((user_id,trip_id))
        gs=[]; ps=[]
        for srcrow in source_rows:
            src=srcrow.asDict(recursive=True)
            seq=int(src["sequence"])
            event_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"canopy:segment-only:{a.run_id}:{u}:{src['event_id']}"))
            g={f.name:src.get(f.name) for f in gps_schema}
            g.update(event_id=event_id,user_id=user_id,trip_id=trip_id)
            gs.append(g)
            cls,mode=mode_for_sequence(seq); now=now_utc_naive()
            p={f.name:None for f in pred_schema}
            p.update(event_id=event_id,user_id=user_id,trip_id=trip_id,sequence=seq,event_time=src["event_time"],
                     predicted_class=cls,predicted_mode=mode,confidence=1.0,
                     model_name="segment-only-benchmark",model_version="v1",
                     processor_entered_at=now,feature_compute_started_at=now,
                     features_processed_at=now,predicted_at=now)
            ps.append(p)
        gps_users.append(gs); pred_users.append(ps)

    for start in range(0,a.points_per_user,a.sequences_per_batch):
        stop=min(start+a.sequences_per_batch,a.points_per_user)
        gb=[]; pb=[]
        for u in range(a.users):
            gb.extend(gps_users[u][start:stop]); pb.extend(pred_users[u][start:stop])
        spark.createDataFrame(gb,schema=gps_schema).write.format("delta").mode("append").saveAsTable(gps_name)
        spark.createDataFrame(pb,schema=pred_schema).write.format("delta").mode("append").saveAsTable(pred_name)
        print("SEGMENT_INPUT_BATCH",{"run_id":a.run_id,"sequence_start":start+1,"sequence_stop":stop,
              "gps_rows":len(gb),"prediction_rows":len(pb)})
        if stop<a.points_per_user and a.batch_interval_ms>0:
            time.sleep(a.batch_interval_ms/1000.0)

    trip_end_at=now_utc_naive()
    end_schema=spark.table(end_name).schema
    rows=[]
    for u,(user_id,trip_id) in enumerate(identities):
        r={f.name:None for f in end_schema}
        r.update(event_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"canopy:segment-only:{a.run_id}:trip_end:{u}")),
                 event_type="trip_ended",schema_version="trip-lifecycle-v1",trip_id=trip_id,user_id=user_id,
                 campaign_id=f"segment-only:{a.run_id}",started_at=source_rows[0]["event_time"],
                 ended_at=source_rows[-1]["event_time"],expected_last_sequence=int(source_rows[-1]["sequence"]),
                 occurred_at=trip_end_at,processing_generation=1,result_owner="databricks",
                 bronze_ingested_at=trip_end_at,parsed_at=trip_end_at)
        rows.append(r)
    spark.createDataFrame(rows,schema=end_schema).write.format("delta").mode("append").saveAsTable(end_name)
    print("SEGMENT_ONLY_INPUT_READY",{"run_id":a.run_id,"users":a.users,"points_per_user":a.points_per_user,
          "trip_end_parsed_at":str(trip_end_at)})

if __name__=="__main__":
    main()
