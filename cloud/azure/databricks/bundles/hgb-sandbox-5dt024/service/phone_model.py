"""Original phone input/result processing; HGB replaces only model prediction."""
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT/'runtime/tools/local',ROOT/'runtime'):
    if str(path) not in sys.path:sys.path.append(str(path))
from model import LocalModel as OriginalModel, distance, stamp
from service.hgb_classifier import VERSION, features

def device_speed(point):
    value=point.get('raw_speed')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=200/3.6:
        return None
    return value*3.6


class PhoneModel(OriginalModel):
    def predict(self,points):
        return super().predict(points)

    def result(self,trip,points):
        points=[p for p in points if stamp(p['event_time'])>=stamp(trip['started_at']) and (not trip.get('ended_at') or stamp(p['event_time'])<=stamp(trip['ended_at']))]
        # Raw events remain unchanged; prefer a speed-bearing fix for duplicate times.
        unique={}
        for p in sorted(points,key=lambda p:device_speed(p) is None):
            unique.setdefault(stamp(p['event_time']),p)
        points=[unique[t] for t in sorted(unique)]
        if sum(device_speed(p) is not None for p in points)<2:
            result=super().result(trip,points)
            result['model_version']=VERSION+'-coordinate-fallback'
            return result
        # Do not fill a sensor outage with noisy coordinate speeds. Keep its gap visible.
        runs=[];run=[];issues=[]
        for a,b in zip(points,points[1:]):
            if device_speed(a) is None or device_speed(b) is None:
                if len(run)>1:runs.append(run)
                run=[];issues.append({'start_time':a['event_time'],'end_time':b['event_time'],'reason':'device_speed_unavailable'})
            else:
                if not run:run=[a]
                run.append(b)
        if len(run)>1:runs.append(run)
        if not runs:raise ValueError('No consecutive speed-bearing GPS measurements')
        results=[super(PhoneModel,self).result(trip,run) for run in runs]
        result=results[0]
        result['segments']=[s for r in results for s in r['segments']]
        result['transit_evidence']=[e for r in results for e in r['transit_evidence']]
        for i,s in enumerate(result['segments']):s['segment_id']=trip['trip_id']+':segment:'+str(i+1)
        issues.extend(e for r in results for e in r['data_quality']['excluded_intervals'])
        result['data_quality']={'version':'phone-speed-quality-v2','status':'partial' if issues else 'complete','excluded_intervals':issues}
        result['model_version']=VERSION
        return result
