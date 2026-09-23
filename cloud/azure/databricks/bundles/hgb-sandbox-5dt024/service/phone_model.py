"""Pure HGB inference adapter; no storage clients and no SpeedTransformer fallback."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib,math
import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from src.aihub.robust_features import canonical_window_features
from src.aihub.ingest import AiHubPoint
from src.aihub.training import ROBUST_FEATURE_COLUMNS
from src.common.geo import haversine_distance_km
ROOT=Path(__file__).resolve().parents[1]
VERSION='hgb-canonical-raw120-16features-sandbox-v1'

def stamp(value):
    value=value if isinstance(value,datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def distance(a,b):
    return haversine_distance_km(a['lat'],a['lon'],b['lat'],b['lon'])*1000

def features(points):
    return canonical_window_features([AiHubPoint(timestamp=stamp(p['event_time']),latitude=p['lat'],longitude=p['lon'],accuracy_m=p.get('accuracy'),altitude_m=p.get('altitude_m')) for p in points],user_id='sandbox',trajectory_id='window',raw_point_count=len(points))

class PhoneModel:
    def __init__(self):
        path=ROOT/'models/mobility_recognition/aihub_canonical_raw120.joblib'
        expected='f1c30c2923bccdb9018dd9d722167a1e7902450ec47ca8408bacfd300e533878'
        self.sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        if self.sha256!=expected:raise ValueError('HGB artifact hash mismatch')
        self.bundle=joblib.load(path)
        if not isinstance(self.bundle['model'],HistGradientBoostingClassifier):raise TypeError('HGB required')
        if tuple(self.bundle['feature_columns'])!=tuple(ROBUST_FEATURE_COLUMNS):raise ValueError('Unexpected 16-feature order')
        if self.bundle['window_duration_seconds']!=120:raise ValueError('120-second artifact required')
        self.classes=list(self.bundle['classes'])
        if set(self.classes)!={'walk','bike','car','bus','rail'}:raise ValueError('Unexpected model classes')

    def predict_window(self,points):
        f=features(points)
        if set(f)!=set(ROBUST_FEATURE_COLUMNS):raise ValueError('Calculator must produce exactly 16 features')
        frame=pd.DataFrame([f],columns=self.bundle['feature_columns'])
        probabilities=self.bundle['model'].predict_proba(frame)[0]
        return dict(zip(self.classes,map(float,probabilities))),f

    def result(self,trip,points):
        from service.transit_fusion import fuse
        start,end=stamp(trip['started_at']),stamp(trip['ended_at'])
        if end<start:raise ValueError('Invalid trip time range')
        unique={}
        for p in points:
            when=stamp(p['event_time'])
            if not start<=when<=end:continue
            if not all(isinstance(p.get(k),(int,float)) and not isinstance(p.get(k),bool) and math.isfinite(p[k]) for k in ['lat','lon']):raise ValueError('Invalid coordinates')
            if not -90<=p['lat']<=90 or not -180<=p['lon']<=180:raise ValueError('Coordinate range')
            if when in unique and unique[when]!=p:raise ValueError('Conflicting duplicate GPS timestamp')
            unique[when]=p
        ordered=[unique[k] for k in sorted(unique)]
        issues=[];runs=[];run=[]
        for a,b in zip(ordered,ordered[1:]):
            seconds=(stamp(b['event_time'])-stamp(a['event_time'])).total_seconds()
            reason=None
            if seconds>120:reason='collection_gap'
            elif any(isinstance(p.get('accuracy'),bool) or not isinstance(p.get('accuracy'),(int,float)) or not math.isfinite(p['accuracy']) or not 0<=p['accuracy']<=100 for p in (a,b)):reason='poor_accuracy'
            elif distance(a,b)/seconds*3.6>200:reason='speed_above_200_kmh'
            if reason:
                if len(run)>1:runs.append(run)
                run=[];issues.append({'start_time':stamp(a['event_time']).isoformat(),'end_time':stamp(b['event_time']).isoformat(),'reason':reason})
            else:
                if not run:run=[a]
                run.append(b)
        if len(run)>1:runs.append(run)
        segments=[];evidence=[];history=[]
        for run in runs:
            anchor=stamp(run[0]['event_time']);last=stamp(run[-1]['event_time'])
            # Original fixed, half-open 120s windows; incomplete tails are NOT padded or classified.
            while anchor+timedelta(seconds=120)<=last:
                boundary=anchor+timedelta(seconds=120)
                chunk=[p for p in run if anchor<=stamp(p['event_time'])<boundary]
                if len(chunk)>=2:
                    probs,feat=self.predict_window(chunk)
                    group=[p for p in run if anchor<=stamp(p['event_time'])<=boundary]
                    decision,context,reference=fuse(probs,group,history)
                    for station in context.get('subway_current_observed_station_ids',[]):
                        item=(str(station),str(context.get('matched_subway_line')))
                        if item not in history:history.append(item)
                    seg={'segment_id':trip['trip_id']+':segment:'+str(len(segments)+1),'mode':decision['final_mode'],'start_time':stamp(group[0]['event_time']).isoformat(),'end_time':stamp(group[-1]['event_time']).isoformat(),'distance_m':sum(distance(a,b) for a,b in zip(group,group[1:])),'confidence':decision['decision_confidence']}
                    segments.append(seg)
                    evidence.append({'window_start':anchor.isoformat(),'window_end':boundary.isoformat(),'probabilities':probs,'features':feat,'decision':decision,'context':context,'reference':reference})
                else:issues.append({'start_time':anchor.isoformat(),'end_time':boundary.isoformat(),'reason':'insufficient_points'})
                anchor=boundary
            if anchor<last:issues.append({'start_time':anchor.isoformat(),'end_time':last.isoformat(),'reason':'incomplete_120s_window'})
        # Account for every unclassified interval; never claim complete coverage for missing edges.
        cursor=start
        for seg in segments:
            a,b=stamp(seg['start_time']),stamp(seg['end_time'])
            if a>cursor:issues.append({'start_time':cursor.isoformat(),'end_time':a.isoformat(),'reason':'unclassified_interval'})
            cursor=max(cursor,b)
        if cursor<end:issues.append({'start_time':cursor.isoformat(),'end_time':end.isoformat(),'reason':'unclassified_interval'})
        return {'trip_id':trip['trip_id'],'model_version':VERSION,'segments':segments,'transit_evidence':evidence,'status':'READY' if segments else 'COLLECTING','endpoint_observations':[{k:p.get(k) for k in ['event_time','lat','lon','accuracy']} for p in ([ordered[0],ordered[-1]] if ordered else [])],'data_quality':{'version':'hgb-sandbox-quality-v1','status':'partial' if issues else 'complete','excluded_intervals':issues}}
