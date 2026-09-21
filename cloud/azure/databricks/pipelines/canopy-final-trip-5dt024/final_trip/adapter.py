"""Fail-closed adapter from the canonical Silver contract to the tested finalizer."""
from datetime import datetime, timezone
import hashlib
import json
import math


class NotReady(Exception):
    """Input is still arriving. Leave the lifecycle unchanged for the next run."""


def iso(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime):
        raise ValueError('expected timestamp')
    # Spark TIMESTAMP arrives as naive UTC because the session is explicitly UTC.
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc).isoformat()


def positive_int(value, name):
    if type(value) is not int or value < 1:
        raise ValueError('invalid ' + name)
    return value


def envelope(trip, segments, ends):
    if trip.get('status') != 'processing' or trip.get('result_owner') != 'databricks':
        raise ValueError('lifecycle not assigned to Databricks')
    generation = positive_int(trip['processing_generation'], 'generation')
    expected = positive_int(trip['expected_last_sequence'], 'expected_last_sequence')
    identity = (trip['trip_id'], trip['user_id'], generation)
    def check(row):
        if (row.get('trip_id'), row.get('user_id'), row.get('processing_generation')) != identity:
            raise ValueError('Silver identity/generation mismatch')
    if not ends or not segments:
        raise NotReady('waiting for trip end and segments')
    for end in ends:
        check(end)
        if end.get('expected_last_sequence') != expected or end.get('result_owner') != 'databricks':
            raise ValueError('trip end conflicts with lifecycle')
    unique = {}
    for row in segments:
        check(row)
        index = positive_int(row['segment_index'], 'segment_index')
        normalized = {**row}
        for field in ('start_time', 'end_time', 'segmented_at', 'latest_prediction_at', 'trip_end_parsed_at'):
            normalized[field] = iso(row[field])
        if index in unique and unique[index] != normalized:
            raise ValueError('conflicting duplicate segment')
        unique[index] = normalized
    rows = [unique[k] for k in sorted(unique)]
    if sorted(unique) != list(range(1, len(rows) + 1)):
        raise NotReady('segment index gap')
    cursor = 1
    ids = set()
    for row in rows:
        start = positive_int(row['start_sequence'], 'start_sequence')
        end = positive_int(row['end_sequence'], 'end_sequence')
        if end < start or end > expected:
            raise ValueError('segment sequence outside stopped trip')
        if start != cursor:
            if start < cursor:
                raise ValueError('overlapping segment ranges')
            raise NotReady('segment range gap')
        if row['point_count'] != end - start + 1:
            raise ValueError('segment point count mismatch')
        if row['segment_id'] in ids:
            raise ValueError('duplicate segment identity')
        ids.add(row['segment_id'])
        if row['mode'] not in {'walk', 'bike', 'car', 'bus', 'rail'}:
            raise ValueError('unsupported upstream mode')
        if isinstance(row['distance_m'], bool) or not math.isfinite(row['distance_m']) or row['distance_m'] < 0:
            raise ValueError('invalid distance')
        if not row.get('model_name'):
            raise ValueError('missing upstream model identity')
        cursor = end + 1
    if cursor != expected + 1:
        raise NotReady('last segment has not reached stopped sequence')
    versions = sorted({row['model_name'] + ':' + str(row.get('model_version') or 'unversioned') for row in rows})
    context = {k: trip[k] for k in ('trip_id', 'user_id', 'campaign_id', 'started_at', 'ended_at', 'processing_generation')}
    return {
        'trip': context,
        'result': {'trip_id': trip['trip_id'], 'model_version': '|'.join(versions),
                   # Spark to_json omits null fields; the ML contract allows
                   # confidence=None. Preserve unknown confidence as null.
                   'segments': [{**{k: r[k] for k in ('segment_id', 'mode', 'start_time', 'end_time', 'distance_m')},
                                 'confidence': r.get('confidence')} for r in rows]},
        # Stable across replays. A wall-clock completion time would break the Gold hash.
        'completed_at': max([iso(trip['ended_at'])] + [r['segmented_at'] for r in rows]),
    }


def finalize(trip, segments, ends, points):
    from finalize_trip_pipeline import build_final_trip, canonical
    from commute import verify
    if trip.get('status') not in ('processing', 'ready'):
        raise ValueError('lifecycle is not eligible for finalization')
    if trip.get('status') == 'ready' and trip.get('endpoint_observations'):
        raise ValueError('ready lifecycle already has endpoint proof')
    wanted = set(range(1, trip['expected_last_sequence'] + 1))
    if any(p.get('trip_id') != trip['trip_id'] or p.get('user_id') != trip['user_id'] for p in points):
        raise ValueError('GPS ownership mismatch')
    by_sequence = {}
    for p in points:
        normalized = {**p, 'event_time': iso(p['event_time'])}
        if p['sequence'] in by_sequence and by_sequence[p['sequence']] != normalized:
            raise ValueError('conflicting GPS sequence')
        by_sequence[p['sequence']] = normalized
    if set(by_sequence) != wanted:
        raise NotReady('GPS endpoint/completeness proof pending')
    ordered = [by_sequence[k] for k in sorted(by_sequence)]
    from model import distance, stamp
    from cloud.azure.pipelines.gps_streaming.quality import transition_issue, QUALITY_VERSION
    issues = []
    for left, right in zip(ordered, ordered[1:]):
        seconds = (stamp(right['event_time']) - stamp(left['event_time'])).total_seconds()
        speed = distance(left, right) / seconds * 3.6 if seconds > 0 else 0
        issue = transition_issue(left.get('accuracy'), right.get('accuracy'), seconds, speed)
        if issue: issues.append({'from_sequence': left['sequence'], 'to_sequence': right['sequence'], 'reason': issue})
    source = envelope({**trip, 'status': 'processing'}, segments, ends)
    source['result']['endpoint_observations'] = [ordered[0], ordered[-1]]
    source['result']['data_quality'] = {'status': 'partial' if issues else 'complete',
                                      'version': QUALITY_VERSION, 'excluded_intervals': issues}
    document = build_final_trip(source, lifecycle=trip)
    document['commute_verified'] = verify(document, ordered)
    document['segment_source'] = 'canonical-silver.mode_segments'
    document['finalization_hash'] = hashlib.sha256(canonical({k: v for k, v in document.items() if k != 'finalization_hash'}).encode()).hexdigest()
    return document


def publish_with_endpoint_repair(store, document):
    """Enrich a previously finalized result without changing its financial result."""
    from finalize_trip_pipeline import publish_cosmos, verify_document
    from services.cosmos_service import Conflict
    verify_document(document)
    for _ in range(5):
        current = store.read(document['trip_id'], document['user_id'])
        if not current or current.get('status') != 'ready' or current.get('endpoint_observations') or not document.get('endpoint_observations'):
            return publish_cosmos(store, document)
        if current.get('result_owner') != 'databricks':
            raise ValueError('metadata repair requires Databricks ownership')
        for key in ('trip_id','user_id','campaign_id','processing_generation','started_at','ended_at',
                    'segments','confirmed_trip','carbon','model_version'):
            if current.get(key) != document.get(key):
                raise ValueError('metadata repair cannot change ' + key)
        repaired = {**current, **{k: document[k] for k in
            ('endpoint_observations','data_quality','commute_verified','finalization_hash')}}
        if current.get('reward_settlement_status') == 'insufficient_gps':
            repaired.update(reward_settlement_terminal=False, reward_retry_at='')
        try:
            store.replace(repaired)
            return 'endpoint_metadata_repaired'
        except Conflict:
            continue
    raise RuntimeError('metadata repair conflicted repeatedly')
