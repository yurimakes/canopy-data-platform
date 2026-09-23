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
VERSION='hgb-canonical-raw120-16features-production-flow-v3'

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
        # Preserve the existing 20-step output cadence and 200-step context.
        # HGB consumes 16 calculated features instead of a padded speed tensor.
        if len(points)<2:return []
        rows=[];begin=0
        for end in range(20,len(points)-1+20,20):
            end=min(end,len(points)-1)
            probabilities,_=self.predict_window(points[max(0,end-200):end+1])
            mode=max(probabilities,key=probabilities.get)
            rows.append({'begin':begin,'end':end,'mode':mode,'confidence':probabilities[mode],'probabilities':probabilities})
            begin=end
        return rows
