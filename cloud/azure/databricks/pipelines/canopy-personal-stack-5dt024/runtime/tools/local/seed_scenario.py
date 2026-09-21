"""자격 충족·지급·재실행 검증용 합성 데이터. 실제 GPS/ML 결과와 별도 저장."""
import json
import sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'apps/api'),str(Path(__file__).parent)]
from services.trip_carbon import finalize_result
from business import issue


def main():
    output=ROOT/'.local-data/scenarios/baseline'
    inputs=output/'inputs';inputs.mkdir(parents=True,exist_ok=True)
    today=datetime.now(timezone.utc).date()
    monday=today-timedelta(days=today.weekday()+21)
    users=[];trips=[];bundles=[]
    for i in range(6):
        uid=f'local-scenario-user-{i+1}'
        user={'user_id':uid,'campaign_id':'local_scenario','department_id':'local-department',
              'nickname':f'검증 사용자 {i+1}','campaign_joined_at':str(monday-timedelta(days=14))+'T00:00:00+00:00'}
        users.append(user)
        for week in range(2):
            day=monday+timedelta(days=7*week)
            bundles.append(issue(output/'state',user,day,[]))
            for j in range(6):
                start=datetime.combine(day,datetime.min.time(),timezone.utc)+timedelta(days=j//2,hours=1+8*(j%2))
                end=start+timedelta(minutes=20)
                tid=f'{uid}-w{week}-t{j}'
                mode='car' if week==0 else 'walk'
                segment={'segment_id':tid+':1','mode':mode,'model_prediction':mode,'start_time':start.isoformat(),'end_time':end.isoformat(),'distance_m':5000,'confidence':None}
                trip={'id':tid,'trip_id':tid,'user_id':uid,'campaign_id':user['campaign_id'],'status':'ready',
                    'started_at':start.isoformat(),'ended_at':end.isoformat(),'updated_at':end.isoformat(),
                    'model_version':'synthetic-policy-scenario','is_mock':True,'processing_generation':1,'segments':[segment]}
                finalize_result(trip,trip['segments'],end.isoformat());trips.append(trip)
    for name,rows in [('users',users),('trips',trips),('mission_bundles',bundles)]:
        (inputs/(name+'.json')).write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    print(str(inputs),len(users),'users',len(trips),'synthetic trips')


if __name__=='__main__':main()
