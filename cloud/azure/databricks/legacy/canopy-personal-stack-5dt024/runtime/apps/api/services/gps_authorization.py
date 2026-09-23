"""Authenticate GPS ownership without rewriting the raw observation."""
from .trip_service import ApiError

def authorize(payload, headers, api, authenticate):
    user=authenticate({k.lower():v for k,v in headers.items()})
    if not isinstance(payload,dict) or payload.get('user_id')!=user:
        raise ApiError(403,'forbidden','GPS account does not match login')
    if not isinstance(payload.get('trip_id'),str):raise ApiError(400,'invalid_trip','trip_id required')
    trip=api.get(payload['trip_id'],user)
    if payload.get('device_id')!=trip.get('device_id'):
        raise ApiError(403,'forbidden','GPS device does not match Trip')
    seq=payload.get('sequence')
    if isinstance(seq,bool) or not isinstance(seq,int) or seq<1:
        raise ApiError(400,'invalid_sequence','positive GPS sequence required')
    # An accepted delivery may be retried after stop if its acknowledgement was lost.
    if trip['status']!='collecting' and seq>(trip.get('expected_last_sequence') or 0):
        raise ApiError(409,'trip_closed','sequence exceeds stopped Trip boundary')
    return trip
