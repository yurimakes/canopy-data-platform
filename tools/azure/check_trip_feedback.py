"""Opt-in live feedback regression using existing test credentials and Cosmos.

Creates three synthetic Trips, never modifies existing Trips or Azure settings.
Run with apps/api/.venv/Scripts/python.exe tools/azure/check_trip_feedback.py --run.
Evidence stays in ignored apps/api/.local-data/azure-trip-feedback.json.
"""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from azure.cosmos import CosmosClient
from jsonschema import validate

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'apps/api/.local-data'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Send synthetic test Trips and feedback to Azure')
    args = parser.parse_args()
    if not args.run:
        parser.error('--run is required to send live test data')
    cfg = json.loads((DATA/'azure-test-access.json').read_text(encoding='utf-8'))
    owner = 'canopy-e2e-test'
    db = CosmosClient(cfg['cosmos_endpoint'], credential=cfg['cosmos_readonly_key']).get_database_client('canopy-db')
    trips, feedback = db.get_container_client('trips'), db.get_container_client('trip_feedback')
    schema = json.loads((ROOT/'shared/schemas/trip_feedback.schema.json').read_text(encoding='utf-8'))
    report = {'source':'synthetic HTTP test, not a real iPhone test', 'trips':[], 'checks':{}}

    def save():
        (DATA/'azure-trip-feedback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    def call(path, body=None, expected=(200,), user=owner):
        headers = {'x-functions-key':cfg['key'], 'Content-Type':'application/json'}
        if user: headers['Authorization'] = 'Bearer '+cfg['tokens'][user]
        req = Request(cfg['host']+'/api/'+path, headers=headers,
                      data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'POST')
        try:
            with urlopen(req, timeout=45) as response: status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        assert status in expected, f'{path}: HTTP {status}; expected {expected}'
        return json.loads(raw)

    for has_issue, text in ((False, None), (True, '버스 구간이 실제 이동과 달랐습니다.'), (True, None)):
        start = {'request_id':str(uuid.uuid4()), 'device_id':'synthetic-feedback-test'}
        trip = call('trips/start', start, (201,))
        trip_id = trip['trip_id']; path = 'trips/'+trip_id
        row = {'trip_id':trip_id, 'user_id':owner, 'has_issue':has_issue}
        report['trips'].append(row); save()
        assert call('trips/start', start)['trip_id'] == trip_id
        call(path+'/feedback', {'request_id':'not-ready','has_issue':True}, (409,))
        now = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
        event = {'schema_version':'canopy.gps.collector.v0.2','event_id':str(uuid.uuid4()),
                 'trip_id':trip_id,'user_id':owner,'device_id':start['device_id'],'sequence':1,
                 'event_time':now,'received_at':now,'lat':37.5665,'lon':126.978,'accuracy':150,'speed':None,
                 'altitude_m':None,'vertical_accuracy_m':None,'course_deg':None,'source':'expo-location.foreground',
                 'collection_mode':'user','label':None,'quality_flags':['accuracy_above_100m','speed_unavailable','course_unavailable'],
                 'raw_location':{'timestamp':int(time.time()*1000),'coords':{'latitude':37.5665,'longitude':126.978,
                     'accuracy':150,'speed':None,'heading':None,'altitude':None,'altitudeAccuracy':None}},
                 'test_context':'synthetic desktop feedback regression; exclude from training'}
        call('gps',event,(202,)); row['gps_event']=event
        began = time.monotonic()
        result = call(path+'/stop',{'expected_last_sequence':1},(200,202))
        row['stop_response_seconds']=round(time.monotonic()-began,3)
        row['stop_response_status']=result['status']
        for _ in range(30):
            if result['status']=='ready': break
            assert result['status']=='processing', result['status']
            time.sleep(2); result=call(path)
        assert result['status']=='ready'
        assert result['confirmed_trip']['mode_source']=='model_prediction'
        assert all(s['confirmed_mode'] is None for s in result['segments'])
        before=trips.read_item(trip_id,partition_key=owner)
        assert call(path+'/stop',{'expected_last_sequence':1})['confirmed_trip']==result['confirmed_trip']
        body={'request_id':str(uuid.uuid4()),'has_issue':has_issue,'feedback_text':text}
        call(path+'/feedback',body,(401,),user=None)
        call(path+'/feedback',body,(403,404),user='hayden-device-test')
        for invalid in ({**body,'has_issue':'yes'},{**body,'feedback_text':'x'*501},{**body,'segments':[]}):
            call(path+'/feedback',invalid,(400,))
        accepted=call(path+'/feedback',body)
        assert accepted['feedback_status']==('submitted' if has_issue else 'no_issue')
        assert accepted['review_required']==has_issue
        after=trips.read_item(trip_id,partition_key=owner)
        for key,value in before.items():
            if key not in ('_etag','_ts'): assert after[key]==value,key+' was modified by feedback'
        documents=list(feedback.query_items(
            query='SELECT * FROM c WHERE c.trip_id=@trip',parameters=[{'name':'@trip','value':trip_id}],partition_key=owner))
        assert len(documents)==int(has_issue)
        if has_issue:
            document=documents[0]; validate(document,schema)
            assert document['feedback_text']==text and document['review_status']=='pending'
            assert document['trip_flag_applied'] and document['feedback_id']==accepted['feedback_id']
        for _ in range(3):
            assert call(path+'/feedback',body)==accepted
        assert trips.read_item(trip_id,partition_key=owner)['_etag']==after['_etag']
        assert len(list(feedback.query_items(query='SELECT * FROM c WHERE c.trip_id=@trip',
            parameters=[{'name':'@trip','value':trip_id}],partition_key=owner)))==int(has_issue)
        call(path+'/feedback',{**body,'has_issue':not has_issue,'feedback_text':None},(409,))
        call(path+'/confirm',{},(410,))
        assert trips.read_item(trip_id,partition_key=owner)['_etag']==after['_etag']
        row.update(feedback_id=accepted.get('feedback_id'),feedback_status=accepted['feedback_status'],
                   result_unchanged=True,duplicate_count=len(documents),passed=True)
        save(); print('PASS',trip_id,row['feedback_status'],'stop_seconds='+str(row['stop_response_seconds']),flush=True)
    report['checks']={key:True for key in ('no_issue_no_document','issue_with_text','issue_without_text',
        'duplicate_is_read_only','result_and_carbon_unchanged','ownership_and_validation','direct_correction_retired',
        'start_stop_gps_ingestion','carbon_before_feedback')}
    save(); print('Azure feedback regression passed. Evidence:',DATA/'azure-trip-feedback.json')


if __name__=='__main__':
    main()
