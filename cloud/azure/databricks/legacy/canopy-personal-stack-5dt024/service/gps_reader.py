"""Retain the phone speed already present in Silver instead of dropping it."""
from datetime import timezone


def merge_history(points,previous):
    by_sequence={p['sequence']:p for p in points}
    for point in previous:
        old=by_sequence.get(point['sequence'])
        if old is not None and old!=point:raise ValueError('Conflicting fast/history GPS')
        by_sequence[point['sequence']]=point
    return list(by_sequence.values())


def read_gps(spark,table,trip,history_table=None):
    from trip_delta_store import table_name
    from pyspark.sql import functions as F
    table_name(table)
    rows=spark.table(table).where((F.col('user_id')==trip['user_id'])&(F.col('trip_id')==trip['trip_id'])&(F.col('sequence')<=trip['expected_last_sequence'])).collect()
    points=[]
    for row in rows:
        point=row.asDict(recursive=True)
        event=point['event_time']
        if hasattr(event,'isoformat'):
            point['event_time']=(event.replace(tzinfo=timezone.utc) if event.tzinfo is None else event).isoformat()
        points.append({k:point.get(k) for k in ('user_id','trip_id','sequence','event_time','lat','lon','accuracy','raw_speed')})
    expected=trip['expected_last_sequence']
    if history_table and {p['sequence'] for p in points}!=set(range(1,expected+1)):
        # Old Trips can predate the fast consumer's Event Hub retention window.
        # Query legacy Silver only then; do not silently lose retryable history.
        previous=read_gps(spark,history_table,trip)
        points=merge_history(points,previous)
    return points
