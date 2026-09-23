"""Install the retained reference CSVs from a local CANOPY checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
NAMES = ('seoul_bus_stops.csv','seoul_bus_route_stops.csv','subway_stations.csv','korail_stations.csv','subway_timetable.csv')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, help='Folder containing all five retained reference CSVs')
    p.add_argument('--out', type=Path, default=ROOT/'.local-data/transit')
    args = p.parse_args()
    candidates = [args.source] if args.source else [ROOT/'data/processed/transit_context', ROOT/'legacy/original-data-platform/data/processed/transit_context', ROOT/'runtime-assets/transit', ROOT/'assets/transit', ROOT/'cloud/azure/databricks/bundles/production-trip/runtime/runtime-assets/transit', ROOT/'cloud/azure/databricks/bundles/hgb-sandbox-5dt024/runtime/runtime-assets/transit', ROOT/'cloud/azure/databricks/legacy/canopy-personal-stack-5dt024/runtime/runtime-assets/transit']
    source = next((d.resolve() for d in candidates if d and all((d/n).is_file() for n in NAMES)), None)
    if source is None:
        raise SystemExit('Set --source to the retained public reference CSV folder. See DATA_SOURCES.md.')
    destination = args.out.resolve()
    if source == destination:
        raise SystemExit('Source and destination must differ')
    destination.mkdir(parents=True,exist_ok=True)
    files = {}
    for name in NAMES:
        origin = source/name
        shutil.copy2(origin,destination/name)
        files[name] = {'sha256':digest(origin),'bytes':origin.stat().st_size}
    (destination/'provenance.json').write_text(json.dumps({'source':'retained public reference CSVs; see DATA_SOURCES.md','network_fetch':False,'files':files},indent=2)+'\n',encoding='utf-8')
    print('Installed five local transit reference CSVs; no upstream clone or fetch.')

if __name__ == '__main__':
    main()
