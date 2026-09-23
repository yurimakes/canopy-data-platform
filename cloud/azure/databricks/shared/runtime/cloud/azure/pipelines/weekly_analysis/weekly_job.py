"""Standalone weekly Job: snapshot inputs, run shared transforms, publish atomically.

The Job never writes a reward payment. Uses existing Cosmos/Blob resources only.
"""
import argparse,json,sys,tempfile,inspect
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(inspect.currentframe().f_code.co_filename).resolve().parents[4]
for folder in (ROOT,ROOT/'tools/local',ROOT/'apps/api'):
    if str(folder) not in sys.path:sys.path.insert(0,str(folder))

def export_inputs(database,state_container,folder,trips_container='trips',managed_trips=None,feature_containers=False):
    from services.community_runtime import CosmosDocuments
    from reward_baselines import week_of
    from weekly_ledger import validate_paid_ledger
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    # Explicit projection excludes credentials, tokens, addresses and devices.
    users=list(database.get_container_client('users').query_items(query='SELECT c.user_id,c.campaign_id,c.department_id,c.campaign_joined_at,c.campaign_left_at,c.created_at FROM c WHERE IS_DEFINED(c.user_id) AND IS_DEFINED(c.campaign_id)',enable_cross_partition_query=True))
    trips=managed_trips if managed_trips is not None else list(database.get_container_client(trips_container).query_items(query="SELECT * FROM c WHERE c.type='trip' AND c.status='ready' AND (NOT IS_DEFINED(c.is_mock) OR c.is_mock=false)",enable_cross_partition_query=True))
    by_trip={(t['campaign_id'],t['user_id'],t['trip_id']):t for t in trips}
    from services.feature_documents import FeatureDocuments
    def documents(campaign,name):return FeatureDocuments(database,campaign,name) if feature_containers else CosmosDocuments(state_container,campaign,name)
    ledger=[];bundles=[];events=[]
    for campaign in sorted({u['campaign_id'] for u in users}):
        for r in documents(campaign,'bonus-rewards').all():
            key=(campaign,r.get('user_id'),r.get('trip_id'))
            if r.get('kind')!='trip' or r.get('status')!='paid' or key not in by_trip:continue
            if (by_trip[key].get('start_context') or {}).get('simulation'):continue
            week=r.get('week') or week_of(r['created_at'])
            ledger.append({'reward_id':r['id'],'trip_id':r['trip_id'],'user_id':r['user_id'],'campaign_id':campaign,
                'week':datetime.strptime(week+'-1','%G-W%V-%u').date().isoformat(),'week_label':week,'points':r['points'],'status':'paid'})
        bundles.extend(documents(campaign,'missions').all())
        events.extend(documents(campaign,'mission-events').all())
    outputs={'users':users,'trips':trips,'mission_bundles':bundles,'mission_events':events,'reward_ledger_history':validate_paid_ledger(ledger)}
    for name,rows in outputs.items():(folder/(name+'.json')).write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    return {name:len(rows) for name,rows in outputs.items()}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cosmos-endpoint',required=True)
    parser.add_argument('--database',default='canopy-db')
    parser.add_argument('--state-container',required=True)
    parser.add_argument('--trips-container',default='trips')
    parser.add_argument('--storage-url',required=True)
    parser.add_argument('--container',required=True)
    parser.add_argument('--identity-secret-scope')
    parser.add_argument('--secret-scope')
    parser.add_argument('--cosmos-secret-key')
    parser.add_argument('--storage-secret-key')
    args=parser.parse_args()
    if not args.cosmos_endpoint.startswith('https://') or not args.storage_url.startswith('https://'):raise ValueError('HTTPS endpoints required')
    from azure.identity import ClientSecretCredential
    from databricks.sdk.runtime import dbutils
    from azure.cosmos import CosmosClient
    from azure.storage.blob import BlobServiceClient
    if args.identity_secret_scope:
        credential=ClientSecretCredential(tenant_id=dbutils.secrets.get(args.identity_secret_scope,'azure-tenant-id'),
            client_id=dbutils.secrets.get(args.identity_secret_scope,'azure-client-id'),
            client_secret=dbutils.secrets.get(args.identity_secret_scope,'azure-client-secret'))
        cosmos_credential=blob_credential=credential
    else:
        if not all((args.secret_scope,args.cosmos_secret_key,args.storage_secret_key)):parser.error('Explicit Cosmos/Blob secret names required')
        cosmos_credential=dbutils.secrets.get(args.secret_scope,args.cosmos_secret_key)
        blob_credential=dbutils.secrets.get(args.secret_scope,args.storage_secret_key)
    db=CosmosClient(args.cosmos_endpoint,credential=cosmos_credential).get_database_client(args.database)
    container=BlobServiceClient(args.storage_url,credential=blob_credential).get_container_client(args.container)
    import weekly
    from publish_weekly import publish
    with tempfile.TemporaryDirectory(prefix='canopy-weekly-') as temporary:
        folder=Path(temporary);export_inputs(db,db.get_container_client(args.state_container),folder/'inputs',args.trips_container)
        from azure.core.exceptions import ResourceNotFoundError
        try:
            pointer=json.loads(container.download_blob('weekly/current.json').readall())
            generation=pointer['generation']
            if len(generation)!=32 or any(c not in '0123456789abcdef' for c in generation):raise ValueError('invalid generation')
            previous=container.download_blob('weekly/generations/'+generation+'/ranking.json').readall()
            (folder/'inputs/previous_ranking.json').write_bytes(previous)
        except ResourceNotFoundError:pass
        try:
            weekly.main(['--runtime','databricks','--exported-ledger','--inputs',str(folder/'inputs'),'--output',str(folder/'weekly'),'--state',str(folder/'state')])
            print(publish(folder/'weekly',container))
        except BaseException:
            # Keep last good pointer; expose only a sanitized failed-run marker.
            container.upload_blob('weekly/last-attempt.json',json.dumps({'completed_at':datetime.now(timezone.utc).isoformat(),
                'stages':{'weekly':{'status':'failed','error':'weekly job failed; inspect private job logs'}}}).encode(),overwrite=True)
            raise

if __name__=='__main__':main()
