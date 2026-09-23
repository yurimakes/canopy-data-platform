"""Durable retries for ready Trips, independent of opening the result screen."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from services.local_documents import LocalDocuments
from azure.cosmos.exceptions import CosmosResourceNotFoundError,CosmosResourceExistsError


def recover(data,trips,points_for,now=None):
    from journey_rewards import settle
    now=now or datetime.now(timezone.utc)
    db=LocalDocuments(Path(data)/'settlement-recovery.sqlite')
    for trip in trips:
        if trip.get('status')!='ready':continue
        key=trip['trip_id']
        try:old=db.read_item(key)
        except CosmosResourceNotFoundError:old=None
        version=trip.get('finalization_hash') or trip.get('updated_at')
        if old and old.get('trip_version')==version:
            if old.get('terminal') or old.get('next_at','')>now.isoformat():continue
        attempts=(old or {}).get('attempts',0)+1
        try:
            result=settle(data,trip,trip,points_for(trip))
            terminal=result.get('status') not in ('processing','awaiting_baseline')
        except Exception as exc:
            result={'status':'retrying','message':type(exc).__name__};terminal=False
        row={'id':key,'trip_version':version,'attempts':attempts,'terminal':terminal,'result':result,
             'next_at':(now+timedelta(seconds=min(300,5*2**min(attempts,6)))).isoformat()}
        if old:db.replace_item(key,row,etag=old['_etag'])
        else:
            try:db.create_item(row)
            except CosmosResourceExistsError:pass
