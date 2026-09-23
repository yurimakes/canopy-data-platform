"""Phone input adapter; original checkpoint, scaler and transit resolver stay intact.

Prefer device speed where supplied. Do not manufacture 200 repeated observations
for a short window: use the checkpoint architecture's padding mask instead.
"""
import math
from model import LocalModel as OriginalModel, distance, stamp

VERSION='speedtransformer-phone-speed-v2-masked-v1-transit-v3'


def device_speed(point):
    value=point.get('raw_speed')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=200/3.6:
        return None
    return value*3.6


class PhoneModel(OriginalModel):
    def predict(self,points):
        import numpy as np
        import pandas as pd
        if len(points)<2:return []
        speeds=[]
        for a,b in zip(points,points[1:]):
            seconds=(stamp(b['event_time'])-stamp(a['event_time'])).total_seconds()
            if seconds<=0:raise ValueError('GPS timestamps must increase')
            speed=device_speed(b)
            if speed is None:speed=distance(a,b)/seconds*3.6
            if not 0<=speed<=200:raise ValueError('Speed outside model domain')
            speeds.append(speed)
        batches=[];masks=[];ends=[]
        for end in range(20,len(speeds)+20,20):
            end=min(end,len(speeds));window=speeds[max(0,end-200):end]
            batches.append(window+[0.]*(200-len(window)))
            masks.append([False]*len(window)+[True]*(200-len(window)));ends.append(end)
        raw=np.asarray(batches,dtype=np.float64)
        scaled=self.scaler.transform(pd.DataFrame(raw.reshape(-1,1),columns=['speed'])).reshape(-1,200,1)
        with self.torch.inference_mode():
            logits=self.model(self.torch.from_numpy(scaled.astype(np.float32)),src_key_padding_mask=self.torch.tensor(masks))
            probs=self.torch.softmax(logits,dim=1).numpy()
        rows=[];begin=0
        for end,prob in zip(ends,probs):
            probabilities={('rail' if str(label)=='train' else str(label)):float(p) for label,p in zip(self.labels.classes_,prob)}
            mode=max(probabilities,key=probabilities.get)
            rows.append({'begin':begin,'end':end,'mode':mode,'confidence':probabilities[mode],'probabilities':probabilities});begin=end
        return rows

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
