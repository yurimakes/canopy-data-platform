"""Use the locally validated model on a complete, owner-scoped GPS batch."""
from pathlib import Path
import sys

def wait_for_gps(read,trip,timeout=600,interval=10,clock=None,sleep=None):
    """Wait only for ingestion lag; malformed/conflicting data fails in infer()."""
    import time
    clock=clock or time.monotonic;sleep=sleep or time.sleep
    expected=trip.get('expected_last_sequence')
    if isinstance(expected,bool) or not isinstance(expected,int) or expected<2:raise ValueError('GPS sequence not complete')
    deadline=clock()+timeout
    while True:
        points=read()
        if {p.get('sequence') for p in points}==set(range(1,expected+1)):return points
        if clock()>=deadline:raise TimeoutError('Curated GPS did not reach the stopped Trip sequence')
        sleep(min(interval,max(0,deadline-clock())))

def infer(trip,points,model=None):
    root=Path(__file__).resolve().parents[4]
    import os
    assets=root/'runtime-assets'
    if assets.exists():
        os.environ.setdefault('CANOPY_SPEED_MODEL_ROOT',str(assets/'speed-model'))
        os.environ.setdefault('CANOPY_KTDB_REFERENCE_ROOT',str(assets/'reference-model'))
        os.environ.setdefault('CANOPY_TRANSIT_REFERENCE_DIR',str(assets/'transit'))
    for path in (root/'apps/api',root/'tools/local'):
        if str(path) not in sys.path:sys.path.insert(0,str(path))
    from model import LocalModel
    from services.trip_processor import validate_result
    expected=trip.get('expected_last_sequence')
    if not isinstance(expected,int) or expected<2:raise ValueError('GPS sequence not complete')
    by_sequence={}
    for point in points:
        if point.get('user_id')!=trip['user_id'] or point.get('trip_id')!=trip['trip_id']:raise ValueError('GPS ownership mismatch')
        seq=point['sequence']
        if seq in by_sequence and by_sequence[seq]!=point:raise ValueError('conflicting GPS sequence')
        by_sequence[seq]=point
    if sorted(by_sequence)!=list(range(1,expected+1)):raise ValueError('GPS sequence not complete')
    points=[by_sequence[i] for i in range(1,expected+1)]
    result=(model or LocalModel()).result(trip,points)
    validate_result(trip,result)
    from commute import verify
    verified=verify({**trip,'status':'ready','data_quality':result.get('data_quality')},points)
    return {k:result[k] for k in ('trip_id','model_version','segments','data_quality','endpoint_observations') if k in result},verified

def read_gps(spark,table,trip):
    from trip_delta_store import table_name
    from pyspark.sql import functions as F
    table_name(table)
    rows=spark.table(table).where((F.col('user_id')==trip['user_id'])&(F.col('trip_id')==trip['trip_id'])&(F.col('sequence')<=trip['expected_last_sequence'])).collect()
    points=[]
    for row in rows:
        point=row.asDict(recursive=True)
        event=point['event_time']
        if hasattr(event,'isoformat'):
            from datetime import timezone
            point['event_time']=(event.replace(tzinfo=timezone.utc) if event.tzinfo is None else event).isoformat()
        points.append({k:point.get(k) for k in ('user_id','trip_id','sequence','event_time','lat','lon','accuracy')})
    return points
