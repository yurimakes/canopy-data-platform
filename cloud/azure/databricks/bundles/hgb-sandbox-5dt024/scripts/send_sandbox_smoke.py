"""Send one marked synthetic 4-minute trip to the dedicated sandbox hub only.
Requires Azure CLI and azure-eventhub. Never writes credentials to disk or stdout.
Dry-run by default. Actual transmission requires --send.
"""
import argparse,json,subprocess,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from azure.eventhub import EventHubProducerClient,EventData

SUBSCRIPTION='27db5ec6-d206-4028-b5e1-6004dca5eeef'
NAMESPACE='evhns-canopy-dev'
HUB='evh-canopy-sandbox-5dt024'

def main():
    p=argparse.ArgumentParser();p.add_argument('--send',action='store_true');p.add_argument('--output',required=True);p.add_argument('--az',default='az');a=p.parse_args()
    now=datetime.now(timezone.utc).replace(microsecond=0);start=now-timedelta(seconds=245)
    trip,user,device=[str(uuid.uuid4()) for _ in range(3)]
    iso=lambda d:d.isoformat().replace('+00:00','Z')
    events=[]
    for i in range(241):
        events.append({'schema_version':'canopy.gps.collector.v0.2','event_id':str(uuid.uuid4()),'user_id':user,'device_id':device,'trip_id':trip,'sequence':i+1,'event_time':iso(start+timedelta(seconds=i)),'received_at':iso(now),'lat':37.55+i*.000008,'lon':126.99,'accuracy':5.0,'speed':0.89,'altitude_m':10.0,'vertical_accuracy_m':2.0,'course_deg':0.0,'source':'expo-location.foreground','quality_flags':[],'collection_mode':'developer','label':'walk','test_kind':'synthetic-hgb-sandbox'})
    # Match the collector contract, including the original location object.
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from gps_ingestion.spark_ingestion import REQUIRED_COLLECTOR_FIELDS
    for event in events:
        event['raw_location']={'timestamp':int(datetime.fromisoformat(event['event_time'].replace('Z','+00:00')).timestamp()*1000),'coords':{'latitude':event['lat'],'longitude':event['lon'],'accuracy':event['accuracy'],'altitude':event['altitude_m'],'speed':event['speed']}}
        missing=set(REQUIRED_COLLECTOR_FIELDS)-set(event)
        if missing:raise ValueError('Synthetic event missing fields: '+str(sorted(missing)))
    events.append({'schema_version':'trip-lifecycle-v1','event_type':'trip_ended','event_id':str(uuid.uuid4()),'trip_id':trip,'user_id':user,'campaign_id':'hgb-sandbox-smoke','started_at':iso(start),'ended_at':iso(start+timedelta(seconds=240)),'expected_last_sequence':241,'occurred_at':iso(now),'processing_generation':1,'result_owner':'databricks','test_kind':'synthetic-hgb-sandbox'})
    record={'trip_id':trip,'user_id':user,'hub':HUB,'namespace':NAMESPACE,'synthetic':True,'sent':False,'events':events}
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    if a.send:
        result=subprocess.run([a.az,'eventhubs','namespace','authorization-rule','keys','list','--resource-group','5dt-2nd-team1','--namespace-name',NAMESPACE,'--name','RootManageSharedAccessKey','--subscription',SUBSCRIPTION,'-o','json'],capture_output=True,text=True)
        if result.returncode:raise RuntimeError('Could not obtain sender credential for the main subscription')
        connection=json.loads(result.stdout)['primaryConnectionString']
        if 'Endpoint=sb://'+NAMESPACE+'.servicebus.windows.net/' not in connection:raise RuntimeError('Unexpected Event Hub namespace')
        with EventHubProducerClient.from_connection_string(connection,eventhub_name=HUB) as client:
            batch=client.create_batch(partition_key=trip)
            for event in events:batch.add(EventData(json.dumps(event)))
            client.send_batch(batch)
        record['sent']=True
        out.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='events'}))
if __name__=='__main__':main()
