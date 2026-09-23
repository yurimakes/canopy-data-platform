"""Original final-segment processing with only the classifier replaced by HGB."""
import sys
import math
from datetime import datetime
from pathlib import Path
from service.hgb_classifier import HgbClassifier, VERSION
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from cloud.azure.pipelines.gps_streaming.quality import transition_issue,QUALITY_VERSION

def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def distance(a,b):
    lat1,lat2=map(math.radians,(a['lat'],b['lat']))
    dlat=lat2-lat1;dlon=math.radians(b['lon']-a['lon'])
    h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371008.8*2*math.asin(min(1,math.sqrt(h)))


class LocalModel(HgbClassifier):
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
        runs=[];run=[];issues=[]
        for a,b in zip(points,points[1:]):
            seconds=(stamp(b['event_time'])-stamp(a['event_time'])).total_seconds()
            issue=transition_issue(a.get('accuracy'),b.get('accuracy'),seconds,distance(a,b)/seconds*3.6)
            if issue:
                if len(run)>1:runs.append(run)
                run=[];issues.append({'start_time':a['event_time'],'end_time':b['event_time'],'reason':issue})
            else:
                if not run:run=[a]
                run.append(b)
        if len(run)>1:runs.append(run)
        rows=[]
        for index,run in enumerate(runs):
            rows.extend({**r,'points':run,'run':index} for r in self.predict(run))
        if not rows:raise ValueError('서로 다른 시각의 GPS가 최소 2개 필요합니다')
        segments=[];evidence=[];station_history=[]
        from transit_fusion import fuse
        for row in rows:
            group=row['points'][row['begin']:row['end']+1]
            decision,context,reference=fuse(row.get('probabilities') or {row['mode']:row['confidence']},group,station_history)
            for sid in context.get('subway_current_observed_station_ids',[]):
                item=(str(sid),str(context.get('matched_subway_line')))
                if item not in station_history:station_history.append(item)
            evidence.append({'start_time':group[0]['event_time'],'end_time':group[-1]['event_time'],'decision':decision,'context':context,'reference':reference})
            row={**row,'mode':decision['final_mode'],'confidence':decision['decision_confidence']}
            segment={'mode':row['mode'],'start_time':group[0]['event_time'],'end_time':group[-1]['event_time'],
                     'distance_m':sum(distance(a,b) for a,b in zip(group,group[1:])), 'confidence':row['confidence']}
            if segments and segments[-1]['mode']==segment['mode'] and segments[-1]['end_time']==segment['start_time']:
                segments[-1]['end_time']=segment['end_time'];segments[-1]['distance_m']+=segment['distance_m']
                segments[-1]['confidence']=min(segments[-1]['confidence'],segment['confidence'])
            else:segments.append(segment)
        for i,s in enumerate(segments):s['segment_id']=trip['trip_id']+':segment:'+str(i+1)
        return {'trip_id':trip['trip_id'],'model_version':VERSION,'segments':segments,'transit_evidence':evidence,
            'endpoint_observations':[{k:p.get(k) for k in ('event_time','lat','lon','accuracy')} for p in (points[0],points[-1])],
            'data_quality':{'version':QUALITY_VERSION,'status':'partial' if issues else 'complete','excluded_intervals':issues}}
