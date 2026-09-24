"""Offline adapter for the team's versioned TransitContext evidence/resolver."""
from pathlib import Path
import os,sys,hashlib
from functools import lru_cache
ROOT=Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def runtime():
    # The KTDB adapter uses the same preserved team package.
    package=Path(os.getenv('CANOPY_KTDB_REFERENCE_ROOT',str(ROOT/'.local-data/reference-model')))
    if not package.exists():package=ROOT/'legacy/original-data-platform'
    if str(package) not in sys.path:sys.path.insert(0,str(package))
    from src.transit_context.resolver import resolve_mode
    from src.transit_context.settings import load_settings
    from src.transit_context.spatial import GeoPointIndex
    import pandas as pd
    folder=Path(os.environ.get('CANOPY_TRANSIT_REFERENCE_DIR',ROOT/'.local-data/transit'))
    tables={};manifest={}
    for name in ('seoul_bus_stops','seoul_bus_route_stops','subway_stations','korail_stations'):
        path=folder/(name+'.csv')
        if path.is_file():
            table=pd.read_csv(path,dtype={'stop_id':str,'route_id':str,'station_id':str,'route_no':str})
            tables[name]=table
            manifest[name]={'rows':len(table),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    indexes={k:GeoPointIndex.from_frame(v) for k,v in tables.items() if k!='seoul_bus_route_stops' and len(v)}
    return resolve_mode,load_settings(),tables,indexes,manifest


def preserve_bus_continuity(decision,probabilities,previous_mode):
    """Do not promote an ongoing ML bus prediction to rail from context alone."""
    if (previous_mode=='bus' and max(probabilities,key=probabilities.get)=='bus'
            and decision['final_mode']=='rail'):
        return {**decision,'final_mode':'bus','rail_subtype':None,
                'decision_confidence':probabilities['bus'],'correction_applied':False,
                'decision_status':'bus_continuity',
                'correction_reason':'Previous final mode and current ML prediction are both bus'}
    return decision


def fuse(probabilities,points,station_history=None,previous_mode=None):
    resolve,settings,tables,indexes,manifest=runtime()
    from src.transit_context.evidence import bus_context,subway_context,korail_context
    context={'bus_applicability':'INSUFFICIENT_REFERENCE','rail_applicability':'INSUFFICIENT_REFERENCE',
             'transit_applicability':'INSUFFICIENT_REFERENCE','context_status':'INSUFFICIENT_REFERENCE'}
    if len(points)<2:return resolve(probabilities,context=context),context,manifest
    coordinates=[(p['lat'],p['lon']) for p in points]
    args={'start_latitude':points[0]['lat'],'start_longitude':points[0]['lon'],
          'end_latitude':points[-1]['lat'],'end_longitude':points[-1]['lon'],'settings':settings}
    if 'seoul_bus_stops' in indexes:
        idx=indexes['seoul_bus_stops'];nearest=idx.nearest_many(coordinates)
        observed=[]
        for _,r in nearest.iterrows():
            if r['distance_m']<=settings.radii_m['bus_stop'] and (not observed or observed[-1]!=str(r['stop_id'])):observed.append(str(r['stop_id']))
        context.update(bus_context(**args,bus_stop_index=idx,bus_stops=tables['seoul_bus_stops'],bus_route_stops=tables.get('seoul_bus_route_stops'),observed_stop_ids=observed))
        context['bus_applicability']='APPLICABLE' if nearest['distance_m'].min()<=5000 else 'NOT_APPLICABLE'
    rail=[]
    if 'subway_stations' in indexes:
        idx=indexes['subway_stations']
        context.update(subway_context(**args,station_index=idx,stations=tables['subway_stations'],ml_rail_probability=probabilities.get('rail',0),trajectory=coordinates,station_history=station_history or ()))
        rail.append('APPLICABLE' if idx.nearest_many(coordinates)['distance_m'].min()<=5000 else 'NOT_APPLICABLE')
    if 'korail_stations' in indexes:
        idx=indexes['korail_stations']
        context.update(korail_context(**args,station_index=idx,ml_rail_probability=probabilities.get('rail',0)))
        rail.append('APPLICABLE' if idx.nearest_many(coordinates)['distance_m'].min()<=20000 else 'NOT_APPLICABLE')
    if rail:context['rail_applicability']='APPLICABLE' if 'APPLICABLE' in rail else 'NOT_APPLICABLE'
    if indexes:
        context['context_status']='READY' if len(indexes)==3 and 'seoul_bus_route_stops' in tables else 'PARTIAL_REFERENCE'
        context['transit_applicability']='APPLICABLE' if 'APPLICABLE' in (context['bus_applicability'],context['rail_applicability']) else 'NOT_APPLICABLE'
    decision=resolve(probabilities,context=context,settings=settings)
    # No geographic reference is not evidence that the model is wrong.
    if not indexes:
        mode=max(probabilities,key=probabilities.get)
        decision.update(final_mode=mode,decision_confidence=probabilities[mode],correction_applied=False,
                        decision_status='insufficient_reference',correction_reason='Transit reference data is not installed; ML-only result')
    decision=preserve_bus_continuity(decision,probabilities,previous_mode)
    return decision,context,{'settings_version':settings.version,'files':manifest}
