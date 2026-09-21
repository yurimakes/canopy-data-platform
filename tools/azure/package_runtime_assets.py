"""Build a versioned, private runtime bundle; never include user GPS or secrets."""
import hashlib,json,zipfile
from pathlib import Path

def package(root,output):
    root=Path(root);output=Path(output);entries={}
    reference=root/'.local-data/reference-model'
    for p in (reference/'src').rglob('*.py'):
        entries['reference-model/'+p.relative_to(reference).as_posix()]=p
    for name in ('data/reference/admin_dong_centroids_2021.csv','data/reference/ktdb_sgis_admin_dong_mapping_2021.csv','config/transit_context.json'):
        entries['reference-model/'+name]=reference/name
    entries['models/ktdb_population_baseline.pkl']=root/'.local-data/models/ktdb_population_baseline.pkl'
    for p in (root/'.local-data/transit').glob('*.csv'):entries['transit/'+p.name]=p
    speed=root/'ml/models/speedtransformer/artifacts/playground_v1'
    for p in speed.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':entries['speed-model/'+p.relative_to(speed).as_posix()]=p
    missing=[str(p) for p in entries.values() if not p.is_file()]
    if missing:raise FileNotFoundError('Missing runtime assets: '+', '.join(missing))
    manifest={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in entries.items()}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,path in entries.items():archive.write(path,name)
        archive.writestr('manifest.json',json.dumps(manifest,indent=2))
    return {'path':str(output),'files':len(entries),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}

if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    print(json.dumps(package(root,root/'.local-data/release/runtime-assets.zip')))
