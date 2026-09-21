from copy import deepcopy
import pytest
from services.trip_processor import validate_result, ProcessingError


def test_endpoint_clock_skew_keeps_original_observations_and_rejects_large_offset():
    trip={'trip_id':'t','started_at':'2026-09-21T00:00:01Z','ended_at':'2026-09-21T00:00:10Z'}
    result={'trip_id':'t','model_version':'real:1','segments':[{'segment_id':'s','mode':'walk','start_time':'2026-09-21T00:00:02Z','end_time':'2026-09-21T00:00:09Z','distance_m':10.,'confidence':None}],
            'endpoint_observations':[{'event_time':'2026-09-21T00:00:00.891Z','lat':37.5,'lon':127.},{'event_time':'2026-09-21T00:00:10.500Z','lat':37.5,'lon':127.}]}
    before=deepcopy(result);validate_result(trip,result);assert result==before
    result['endpoint_observations'][0]['event_time']='2026-09-20T23:59:59.999Z'
    with pytest.raises(ProcessingError,match='endpoint outside Trip'):validate_result(trip,result)


def test_segment_boundary_skew_does_not_permit_overlaps():
    trip={'trip_id':'t','started_at':'2026-09-21T00:00:01Z','ended_at':'2026-09-21T00:00:10Z'}
    segment={'segment_id':'s','mode':'walk','start_time':'2026-09-21T00:00:00.891Z','end_time':'2026-09-21T00:00:10.500Z','distance_m':10.,'confidence':None}
    result={'trip_id':'t','model_version':'real:1','segments':[segment]}
    validate_result(trip,result)
    result['segments'].append({**segment,'segment_id':'s2'})
    with pytest.raises(ProcessingError,match='invalid segment times'):validate_result(trip,result)
