"""Provisional predictions only; never settle a Trip or award a reward."""
import logging
import threading
from datetime import datetime, timezone


def publish_live(store, trip, prediction):
    from services.cosmos_service import Conflict
    current = store.read(trip['trip_id'], trip['user_id'])
    if not current or current.get('status') != 'collecting' or current.get('result_owner') not in (None,'databricks'):
        return False
    old = current.get('live_prediction') or {}
    if old.get('sequence', 0) >= prediction['sequence']:
        return False
    current['live_prediction'] = prediction
    try:
        store.replace(current)  # CAS: a concurrent Stop always wins on retry.
    except Conflict:
        return False
    return True


def start_live_predictions(spark, store, model, table, stop=None):
    stop = stop or threading.Event()

    def run():
        from pyspark.sql import functions as F
        from trip_delta_store import table_name
        table_name(table)
        # Serverless uses Spark Connect, which does not expose newSession().
        # Reuse the initialized session for independent read-only queries.
        session = spark
        while not stop.is_set():
            try:
                trips = list(store.container.query_items(
                    "SELECT TOP 20 * FROM c WHERE c.type='trip' AND c.status='collecting' "
                    "AND (NOT IS_DEFINED(c.result_owner) OR c.result_owner='databricks') ORDER BY c._ts ASC",
                    enable_cross_partition_query=True))
                for trip in trips:
                    if stop.is_set():
                        return
                    rows = (session.table(table).where(
                        (F.col('trip_id') == trip['trip_id']) & (F.col('user_id') == trip['user_id']))
                        .orderBy(F.col('sequence').desc()).limit(201).collect())
                    points = []
                    for row in reversed(rows):
                        p = row.asDict(recursive=True)
                        at = p['event_time']
                        if isinstance(at, datetime):
                            p['event_time'] = (at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at).isoformat()
                        points.append(p)
                    if len(points) < 2:
                        continue
                    latest = points[-1]
                    age = (datetime.now(timezone.utc)-datetime.fromisoformat(latest['event_time'].replace('Z','+00:00'))).total_seconds()
                    if age > 30 or age < -5 or latest['sequence'] <= (trip.get('live_prediction') or {}).get('sequence', 0):
                        continue
                    result = model.result(trip, points)
                    if not result['segments']:
                        continue  # HGB needs a complete 120-second window.
                    segment = result['segments'][-1]
                    publish_live(store, trip, {
                        'mode': segment['mode'], 'confidence': segment['confidence'],
                        'sequence': latest['sequence'], 'observed_at': segment['end_time'],
                        'updated_at': datetime.now(timezone.utc).isoformat(),
                        'model_version': result['model_version'], 'provisional': True,
                    })
            except Exception as exc:
                # Live display failure must not stop final settlement.
                logging.warning('live_prediction_failed error_type=%s', type(exc).__name__)
            stop.wait(3)

    thread = threading.Thread(target=run, name='canopy-live-predictions', daemon=True)
    thread.start()
    return stop, thread
