"""Report segment-only trip_end-to-visible latency and finalizer stage telemetry."""
from __future__ import annotations
import argparse, time
from datetime import datetime, timezone
from pyspark.sql import SparkSession, functions as F

def parse_args():
    p=argparse.ArgumentParser()
    for name in ("catalog","schema","trip-ended-table","segments-table","segment-telemetry-table","run-id"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--users",type=int,required=True)
    p.add_argument("--timeout-seconds",type=int,default=180)
    p.add_argument("--poll-seconds",type=float,default=1.0)
    return p.parse_args()

def now_utc_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def compact(r):
    out={"batch_id":int(r["batch_id"]),"status":r["status"],"affected_probe_ms":float(r["affected_probe_ms"]),
         "batch_total_ms":float(r["batch_total_ms"]),"batch_entered_at":str(r["batch_entered_at"]),
         "batch_finished_at":str(r["batch_finished_at"])}
    for n in ("trip_end_probe_ms","pending_probe_ms","pending_projection_ms","gps_plan_ms","predictions_plan_ms",
              "ready_plan_ms","stabilize_plan_ms","segments_plan_ms","pre_segment_plan_ms","segment_probe_ms","merge_ms"):
        if r[n] is not None: out[n]=float(r[n])
    return out

def main():
    a=parse_args()
    spark=SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    end_name=f"{a.catalog}.{a.schema}.{a.trip_ended_table}"
    seg_name=f"{a.catalog}.{a.schema}.{a.segments_table}"
    tel_name=f"{a.catalog}.{a.schema}.{a.segment_telemetry_table}"
    prefix=f"segment-only:{a.run_id}:trip:"

    deadline=time.monotonic()+a.timeout_seconds
    first_visible={}
    last_heartbeat=-10
    while time.monotonic()<deadline:
        ids=[r["trip_id"] for r in (spark.table(seg_name).where(F.col("trip_id").startswith(prefix))
             .select("trip_id").distinct().collect())]
        observed=now_utc_naive()
        for trip_id in ids: first_visible.setdefault(trip_id,observed)
        if len(first_visible)>=a.users: break
        elapsed=int(a.timeout_seconds-(deadline-time.monotonic()))
        if elapsed-last_heartbeat>=10:
            print("SEGMENT_WAIT",{"elapsed_s":elapsed,"segmented_trips":len(first_visible),"expected":a.users})
            last_heartbeat=elapsed
        time.sleep(a.poll_seconds)
    if len(first_visible)<a.users:
        raise TimeoutError(f"timed out with {len(first_visible)}/{a.users} segmented trips")

    ends=(spark.table(end_name).where(F.col("trip_id").startswith(prefix))
          .select("trip_id","parsed_at","expected_last_sequence"))
    visibility=spark.createDataFrame([(k,v) for k,v in first_visible.items()],
                                     "trip_id string, segments_visible_at timestamp")
    rows=(ends.join(visibility,"trip_id","inner")
          .withColumn("trip_end_to_segments_ms",
              (F.col("segments_visible_at").cast("double")-F.col("parsed_at").cast("double"))*1000.0)
          .collect())

    telemetry_deadline=time.monotonic()+30
    telemetry=[]
    while time.monotonic()<telemetry_deadline:
        telemetry=(spark.table(tel_name)
            .where(F.exists(F.col("affected_trip_ids"),lambda x:x.startswith(prefix)))
            .orderBy("batch_id").collect())
        if any(r["status"] in ("appended","merged") for r in telemetry): break
        time.sleep(a.poll_seconds)

    final_batches=[compact(r) for r in telemetry if r["status"]!="no_trip_end"]
    vals=[float(r["trip_end_to_segments_ms"]) for r in rows]
    print("SEGMENT_ONLY_STAGE_REPORT",{"run_id":a.run_id,"batches":final_batches})
    print("SEGMENT_ONLY_REPORT",{"run_id":a.run_id,"users":a.users,
          "avg_trip_end_to_segments_ms":sum(vals)/len(vals),"max_trip_end_to_segments_ms":max(vals),
          "per_trip":{r["trip_id"]:{"expected_last_sequence":int(r["expected_last_sequence"]),
                                   "trip_end_to_segments_ms":float(r["trip_end_to_segments_ms"])} for r in rows}})

if __name__=="__main__":
    main()
