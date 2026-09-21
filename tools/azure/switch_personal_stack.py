"""Switch the existing mobile API to the migrated personal Databricks stack.
Read-only unless --apply. Existing Cosmos records and API/auth keys stay in place.
"""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import requests
from azure.storage.blob import BlobServiceClient
from deploy_main_api import az,GROUP,APP,ROOT,SUB

UPDATES={'EVENTHUB_NAME':'evh-personal-5dt024','TRIP_EVENTHUB_CONSUMER_GROUP':'canopy-trip-finalization','TRIP_DATABRICKS_JOB_ID':'421770332247848','TRIP_DATABRICKS_DISPATCH_MODE':'resident'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--history-run-id',required=True,type=int);a=p.parse_args()
 settings={r['name']:r['value'] for r in az('functionapp','config','appsettings','list','-g',GROUP,'-n',APP)}
 if settings['COSMOS_TRIPS_DATABASE']!='canopy-db':raise ValueError('Unexpected Cosmos database')
 token=az('account','get-access-token','--resource','2ff814a6-3304-4ab8-85cb-cd0e6f879c1d')['accessToken']
 host=settings['TRIP_DATABRICKS_HOST']
 def get(path):
  r=requests.get(host+'/api/'+path,headers={'Authorization':'Bearer '+token},timeout=40);r.raise_for_status();return r.json()
 history=get('2.1/jobs/runs/get?run_id='+str(a.history_run_id))
 if history['state'].get('result_state')!='SUCCESS':raise ValueError('History migration not successful')
 jobs=get('2.1/jobs/list?limit=100')['jobs']
 for j in jobs:
  s=j['settings'];name=s.get('name','')
  if 'canopy' not in name.lower() or 'canopy-personal-' in name:continue
  if any(s.get(k,{}).get('pause_status')=='UNPAUSED' for k in ['schedule','continuous']):raise ValueError('Old job trigger still enabled: '+name)
  if get('2.1/jobs/runs/list?active_only=true&limit=25&job_id='+str(j['job_id'])).get('runs'):raise ValueError('Old job still running: '+name)
 for item in get('2.0/pipelines?max_results=100').get('statuses',[]):
  if 'canopy' in item.get('name','').lower() and 'canopy-personal-' not in item['name'] and item['state']!='IDLE':raise ValueError('Old pipeline still running')
 worker=get('2.1/jobs/get?job_id=421770332247848')['settings']
 config=json.loads(worker['tasks'][0]['spark_python_task']['parameters'][1])
 if config['database']!='canopy-db':raise ValueError('Worker database mismatch')
 sk=az('storage','account','keys','list','-g',GROUP,'-n','stcanopydev5dt')[0]['value']
 b=BlobServiceClient('https://stcanopydev5dt.blob.core.windows.net',credential=sk).get_container_client('personal-5dt024')
 heartbeat=json.loads(b.download_blob('performance/resident-status.json').readall())
 if heartbeat['state']!='ready' or (datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat['updated_at'])).total_seconds()>60:raise ValueError('Resident worker not ready')
 if get('2.0/pipelines/c54de8c4-1240-4835-97b3-e5db2a835e67')['state']!='RUNNING':raise ValueError('GPS not running')
 out=ROOT/'.local-data/main-review/personal-app-cutover';out.mkdir(exist_ok=True)
 receipt={'settings':UPDATES,'worker_id':heartbeat['worker_id'],'applied':False}
 if a.apply:
  backup=out/'settings-before.json'
  if not backup.exists():backup.write_text(json.dumps(settings))
  for consumer in [UPDATES['TRIP_EVENTHUB_CONSUMER_GROUP'],'personal-5dt024-fast']:
   az('eventhubs','eventhub','consumer-group','create','-g',GROUP,'--namespace-name','evhns-canopy-dev','--eventhub-name',UPDATES['EVENTHUB_NAME'],'--name',consumer)
  identity=az('functionapp','identity','show','-g',GROUP,'-n',APP)['principalId']
  scope=f'/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.EventHub/namespaces/evhns-canopy-dev/eventhubs/'+UPDATES['EVENTHUB_NAME']
  for role in ['Azure Event Hubs Data Sender','Azure Event Hubs Data Receiver']:
   az('role','assignment','create','--assignee-object-id',identity,'--assignee-principal-type','ServicePrincipal','--role',role,'--scope',scope)
  path=out/'updates.json';path.write_text(json.dumps(UPDATES))
  az('functionapp','config','appsettings','set','-g',GROUP,'-n',APP,'--settings','@'+str(path))
  after={r['name']:r['value'] for r in az('functionapp','config','appsettings','list','-g',GROUP,'-n',APP)}
  if any(after.get(k)!=v for k,v in UPDATES.items()):raise ValueError('Settings readback mismatch')
  receipt['applied']=True
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))

if __name__=='__main__':main()
