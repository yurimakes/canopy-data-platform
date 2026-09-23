"""Pure HGB inference adapter; no storage clients and no SpeedTransformer fallback."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib,math
from bisect import bisect_left
import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from src.aihub.robust_features import canonical_window_features
from src.aihub.ingest import AiHubPoint
from src.aihub.training import ROBUST_FEATURE_COLUMNS
from src.common.geo import haversine_distance_km
ROOT=Path(__file__).resolve().parents[1]
VERSION='hgb-canonical-raw120-16features-time-window-v4'

def stamp(value):
    value=value if isinstance(value,datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def distance(a,b):
    return haversine_distance_km(a['lat'],a['lon'],b['lat'],b['lon'])*1000

def features(points):
    return canonical_window_features([AiHubPoint(timestamp=stamp(p['event_time']),latitude=p['lat'],longitude=p['lon'],accuracy_m=p.get('accuracy'),altitude_m=p.get('altitude_m')) for p in points],user_id='sandbox',trajectory_id='window',raw_point_count=len(points))

class HgbClassifier:
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

    def predict(self,points):
        """120-second trailing GPS windows, advanced in elapsed 10-second slots.

        Final settlement covers the initial window and the final tail exactly
        once. A trip shorter than 120 seconds uses only its observed points;
        it is never padded, discarded, or presented as a full training window.
        """
        if len(points)<2:return []
        times=[stamp(p['event_time']) for p in points]
        if any(b<=a for a,b in zip(times,times[1:])):
            raise ValueError('Prediction requires unique, ordered GPS timestamps')
        seconds=int(self.bundle['window_duration_seconds'])
        boundary=times[0]+timedelta(seconds=seconds)
        rows=[];begin=0
        while boundary<=times[-1]:
            # Same half-open selection as the original latest_rolling_window.
            left=bisect_left(times,boundary-timedelta(seconds=seconds))
            right=bisect_left(times,boundary)
            if right-left>=2:
                end=right-1
                if end>begin:
                    probabilities,_=self.predict_window(points[left:right])
                    mode=max(probabilities,key=probabilities.get)
                    rows.append({'begin':begin,'end':end,'mode':mode,
                        'confidence':probabilities[mode],'probabilities':probabilities})
                    begin=end
            boundary+=timedelta(seconds=10)
        if begin<len(points)-1:
            # Final endpoint must not disappear between stride boundaries.
            left=bisect_left(times,times[-1]-timedelta(seconds=seconds))
            selected=points[left:]
            if len(selected)<2:
                raise ValueError('Not enough GPS points in final inference window')
            probabilities,_=self.predict_window(selected)
            mode=max(probabilities,key=probabilities.get)
            rows.append({'begin':begin,'end':len(points)-1,'mode':mode,
                'confidence':probabilities[mode],'probabilities':probabilities})
        return rows
