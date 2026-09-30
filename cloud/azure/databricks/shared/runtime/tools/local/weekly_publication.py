"""Publish a complete immutable generation with one atomic pointer swap."""
import hashlib
import json
import uuid
from pathlib import Path
from contextvars import ContextVar
from functools import wraps

_snapshots=ContextVar('weekly_read_snapshots',default=None)
def consistent_read(fn):
    @wraps(fn)
    def run(*args,**kwargs):
        if _snapshots.get() is not None:return fn(*args,**kwargs)
        token=_snapshots.set({})
        try:return fn(*args,**kwargs)
        finally:_snapshots.reset(token)
    return run

def resolve(path):
    path=Path(path)
    pointer=path.parent/'current.json'
    if path.name in ('current.json','last-attempt.json'):return path
    cache=_snapshots.get()
    key=str(pointer.resolve())
    if cache is not None and key in cache:generation=cache[key]
    else:
        generation=json.loads(pointer.read_text(encoding='utf-8'))['generation'] if pointer.exists() else None
        if cache is not None:cache[key]=generation
    if generation is None:return path
    if not isinstance(generation,str) or len(generation)!=32 or any(c not in '0123456789abcdef' for c in generation):
        raise ValueError('invalid weekly generation')
    return path.parent/'generations'/generation/path.name

def publish(folder,results,report):
    folder=Path(folder);generation=uuid.uuid4().hex
    target=folder/'generations'/generation;target.mkdir(parents=True)
    hashes={}
    for name,value in {**results,'run':report}.items():
        if not name.replace('_','').isalnum():raise ValueError('invalid output name')
        payload=json.dumps(value,ensure_ascii=False,default=str).encode('utf-8')
        (target/(name+'.json')).write_bytes(payload)
        hashes[name]=hashlib.sha256(payload).hexdigest()
    (target/'manifest.json').write_text(json.dumps(hashes),encoding='utf-8')
    for name,digest in hashes.items():
        if hashlib.sha256((target/(name+'.json')).read_bytes()).hexdigest()!=digest:raise ValueError('weekly publication verification failed')
    temp=folder/(generation+'.tmp')
    temp.write_text(json.dumps({'generation':generation,'completed_at':report['completed_at']}),encoding='utf-8')
    temp.replace(folder/'current.json')
    return generation
