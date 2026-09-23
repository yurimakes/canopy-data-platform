"""Worker-safe pure finalization; importing this module never opens Spark."""
import json
import pandas as pd
from downstream_bootstrap import activate
activate()
from final_trip.adapter import finalize, NotReady

def unpack(value):
    # Arrow may represent a null string column as NaN when the whole batch is
    # null. Missing upstream data is pending, not an invalid JSON document.
    return [] if pd.isna(value) else json.loads(value)

def calculate(iterator):
    for frame in iterator:
        rows=[]
        for row in frame.itertuples(index=False):
            trip=json.loads(row.document_json)
            try:
                document=finalize(trip, unpack(row.segments), unpack(row.ends), unpack(row.points))
                rows.append((trip['trip_id'],trip['user_id'],trip['processing_generation'],json.dumps(document,allow_nan=False)))
            except NotReady:
                continue
        yield pd.DataFrame(rows,columns=['trip_id','user_id','processing_generation','document_json'])


