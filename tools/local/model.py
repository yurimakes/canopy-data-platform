"""저장소의 학습된 SpeedTransformer를 CPU에서 실행. 랜덤 결과와 규칙 분류 제외."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from datetime import datetime

ROOT=Path(__file__).resolve().parents[2]
ARTIFACT=ROOT/'ml/models/speedtransformer/artifacts/playground_v1'
VERSION='local-speedtransformer-playground-v1-edgepad-v1'


def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def distance(a,b):
    lat1,lat2=map(math.radians,(a['lat'],b['lat']))
    dlat=lat2-lat1;dlon=math.radians(b['lon']-a['lon'])
    h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371008.8*2*math.asin(min(1,math.sqrt(h)))


class LocalModel:
    def __init__(self):
        import joblib
        import torch
        manifest=json.loads((ARTIFACT/'canopy_manifest.json').read_text())
        for filename,key in [('best_macro_model.pth','checkpoint_sha256'),('scaler.joblib','scaler_sha256'),('label_encoder.joblib','label_encoder_sha256')]:
            if hashlib.sha256((ARTIFACT/'artifacts'/filename).read_bytes()).hexdigest()!=manifest[key]:
                raise ValueError('모델 파일 해시 불일치: '+filename)
        spec=importlib.util.spec_from_file_location('local_speed_architecture',ARTIFACT/'code/model_utils.py')
        architecture=importlib.util.module_from_spec(spec);spec.loader.exec_module(architecture)
        torch.set_num_threads(2)
        self.torch=torch
        self.scaler=joblib.load(ARTIFACT/'artifacts/scaler.joblib')
        self.labels=joblib.load(ARTIFACT/'artifacts/label_encoder.joblib')
        self.model=architecture.TrajectoryTransformer(feature_size=1,num_classes=len(self.labels.classes_),d_model=128,nhead=8,kv_heads=4,num_layers=4,window_size=200,dropout=.1)
        state=torch.load(ARTIFACT/'artifacts/best_macro_model.pth',map_location='cpu',weights_only=True)
        self.model.load_state_dict({k.removeprefix('module.'):v for k,v in state.items()},strict=True)
        self.model.eval()

    def predict(self,points):
        import numpy as np
        import pandas as pd
        if len(points)<2:return []
        speeds=[]
        for a,b in zip(points,points[1:]):
            seconds=(stamp(b['event_time'])-stamp(a['event_time'])).total_seconds()
            if seconds<=0:raise ValueError('GPS 시간은 순번대로 증가해야 합니다')
            kmh=distance(a,b)/seconds*3.6
            if not 0<=kmh<=200:raise ValueError('GPS 계산 속도가 모델 범위 0~200km/h를 벗어났습니다')
            speeds.append(kmh)
        batches=[];ends=[]
        for end in range(20,len(speeds)+20,20):
            end=min(end,len(speeds));window=speeds[max(0,end-200):end]
            # 짧은 여정은 마지막 관측 속도로 200개까지 채움. 로컬 전처리 버전에 명시
            batches.append(window+[window[-1]]*(200-len(window)));ends.append(end)
        raw=np.asarray(batches,dtype=np.float64)
        scaled=self.scaler.transform(pd.DataFrame(raw.reshape(-1,1),columns=['speed'])).reshape(-1,200,1)
        with self.torch.inference_mode():
            probs=self.torch.softmax(self.model(self.torch.from_numpy(scaled.astype(np.float32))),dim=1).numpy()
        rows=[];begin=0
        for end,prob in zip(ends,probs):
            label=str(self.labels.inverse_transform([int(prob.argmax())])[0])
            mode={'train':'rail'}.get(label,label)
            if mode not in ('walk','bike','car','bus','rail'):raise ValueError('알 수 없는 모델 클래스: '+mode)
            rows.append({'begin':begin,'end':end,'mode':mode,'confidence':float(prob.max())});begin=end
        return rows

    def result(self,trip,points):
        # 원본은 보존하고 계산 입력만 여정 경계 안의 고유 측정 시각으로 정리
        start=stamp(trip['started_at']) if trip.get('started_at') else None
        end=stamp(trip['ended_at']) if trip.get('ended_at') else None
        unique={}
        for point in points:
            at=stamp(point['event_time'])
            if (start is None or at>=start) and (end is None or at<=end):
                unique.setdefault(at,point)
        points=[unique[at] for at in sorted(unique)]
        rows=self.predict(points)
        if not rows:raise ValueError('서로 다른 시각의 GPS가 최소 2개 필요합니다')
        segments=[]
        for row in rows:
            group=points[row['begin']:row['end']+1]
            segment={'mode':row['mode'],'start_time':group[0]['event_time'],'end_time':group[-1]['event_time'],
                     'distance_m':sum(distance(a,b) for a,b in zip(group,group[1:])), 'confidence':row['confidence']}
            if segments and segments[-1]['mode']==segment['mode']:
                segments[-1]['end_time']=segment['end_time'];segments[-1]['distance_m']+=segment['distance_m']
                segments[-1]['confidence']=min(segments[-1]['confidence'],segment['confidence'])
            else:segments.append(segment)
        for i,s in enumerate(segments):s['segment_id']=trip['trip_id']+':segment:'+str(i+1)
        return {'trip_id':trip['trip_id'],'model_version':VERSION,'segments':segments}
