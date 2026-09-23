"""Publish validated immutable weekly artifacts, then atomically expose them."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime

def validate(folder):
    pointer=json.loads((folder/'current.json').read_text(encoding='utf-8'))
    generation=pointer['generation']
    if len(generation)!=32 or any(c not in '0123456789abcdef' for c in generation):raise ValueError('invalid generation')
    directory=folder/'generations'/generation
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest.items():
        if not name.replace('_','').isalnum():raise ValueError('invalid artifact name')
        if hashlib.sha256((directory/(name+'.json')).read_bytes()).hexdigest()!=digest:raise ValueError('artifact hash mismatch: '+name)
    report=json.loads((directory/'run.json').read_text(encoding='utf-8'))
    if not report.get('stages') or any(s.get('status')!='passed' for s in report['stages'].values()):raise ValueError('weekly stages are incomplete')
    if report.get('reward_mode')!='trip-ledger-only':raise ValueError('weekly rewards must use paid Trip ledger')
    return pointer,directory,manifest

def publish(folder,container):
    from azure.core import MatchConditions
    from azure.core.exceptions import ResourceNotFoundError
    folder=Path(folder);pointer,directory,manifest=validate(folder)
    target=container.get_blob_client('weekly/current.json')
    try:
        download=target.download_blob();old=json.loads(download.readall());etag=download.properties.etag
        if old.get('generation')==pointer['generation']:return 'already_published'
        if datetime.fromisoformat(old['completed_at'].replace('Z','+00:00'))>=datetime.fromisoformat(pointer['completed_at'].replace('Z','+00:00')):raise ValueError('refusing stale weekly publication')
    except ResourceNotFoundError:etag=None
    prefix='weekly/generations/'+pointer['generation']+'/'
    for name in manifest:
        payload=(directory/(name+'.json')).read_bytes()
        container.upload_blob(prefix+name+'.json',payload,overwrite=True)
        if hashlib.sha256(container.download_blob(prefix+name+'.json').readall()).hexdigest()!=manifest[name]:raise ValueError('readback mismatch')
    container.upload_blob(prefix+'manifest.json',(directory/'manifest.json').read_bytes(),overwrite=True)
    options={'overwrite':True,'etag':etag,'match_condition':MatchConditions.IfNotModified} if etag else {'overwrite':False}
    target.upload_blob(json.dumps(pointer).encode(),**options)
    return 'published'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True,help='Validated weekly generation directory')
    parser.add_argument('--storage-url',required=True)
    parser.add_argument('--container',required=True)
    args=parser.parse_args()
    if not args.storage_url.startswith('https://'):raise ValueError('HTTPS storage URL required')
    from azure.storage.blob import BlobServiceClient
    from azure.identity import DefaultAzureCredential
    target=BlobServiceClient(args.storage_url,credential=DefaultAzureCredential()).get_container_client(args.container)
    print(publish(args.source,target))

if __name__=='__main__':main()
