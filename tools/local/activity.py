"""Account-scoped in-app activity; derived from real persisted results."""
from pathlib import Path
from datetime import datetime,timezone
from services.local_documents import LocalDocuments
from azure.cosmos.exceptions import CosmosResourceExistsError
from services.trip_service import ApiError
from rewards import identity


def notifications(data,user,trips,missions,wallet):
    db=LocalDocuments(Path(data)/'notification-read.sqlite')
    read={r['notification_id'] for r in db.all() if r['user_id']==user['user_id'] and r['campaign_id']==user['campaign_id']}
    items=[]
    def add(key,title,message,time,target):
        nid=identity('notification',user,key)
        items.append({'id':nid,'title':title,'message':message,'time':time,'target':target,'read':nid in read})
    for t in trips:
        if t.get('user_id')!=user['user_id'] or t.get('campaign_id')!=user['campaign_id'] or t.get('is_mock'):continue
        if t.get('status')=='ready':add('trip:'+t['trip_id'],'여정 분석을 마쳤어요','이동 기록에서 탄소 배출량과 분석 결과를 확인하세요.',t.get('ended_at') or t['started_at'],'history')
        if t.get('status')=='failed':add('failed:'+t['trip_id'],'여정 분석을 다시 확인해주세요','이동 기록에서 결과를 열고 처리를 다시 시도할 수 있어요.',t.get('updated_at') or t['started_at'],'history')
    for m in missions.get('data',{}).get('items',[]):
        if m['status']=='claimable':add('mission:'+m['id'],'미션을 달성했어요',m['title']+' · 보상을 받아보세요.',m.get('week') or missions['data']['week'],'missions')
    for r in wallet.get('data',{}).get('items',[]):
        if r['status']=='paid':add('reward:'+r['id'],'보상이 적립됐어요',f"{r['title']} · +{r['amount']} T",r['time'],'rewards')
    items.sort(key=lambda r:r['time'],reverse=True)
    return {'state':'ready','data':{'items':items[:100],'unread':sum(not r['read'] for r in items[:100])}}


def mark_read(data,user,nid,allowed):
    if nid not in allowed:raise ApiError(404,'not_found','알림을 찾을 수 없습니다.')
    row={'id':identity('notification-read',user,nid),'notification_id':nid,'user_id':user['user_id'],'campaign_id':user['campaign_id'],
         'read_at':datetime.now(timezone.utc).isoformat()}
    try:LocalDocuments(Path(data)/'notification-read.sqlite').create_item(row)
    except CosmosResourceExistsError:pass
    return {'status':'read'}


def cumulative_ranking(data,user,users):
    from reward_baselines import paid_trip_history
    from business import read_rows
    totals={}
    run=read_rows(Path(data)/'weekly/run.json') or {}
    source=read_rows(Path(data)/'weekly/reward_ledger.json') if run.get('synthetic') else paid_trip_history(data)
    for r in source:
        if r['campaign_id']!=user['campaign_id']:continue
        totals[r['user_id']]=totals.get(r['user_id'],0)+r['points']
    people={u['user_id']:u for u in users if u.get('campaign_id')==user['campaign_id']}
    def rank(scores,names):
        result=[];previous=None;place=0
        for i,(key,points) in enumerate(sorted(scores.items(),key=lambda x:(-x[1],x[0])),1):
            if points!=previous:place=i
            previous=points
            result.append({'id':key,'name':names.get(key,'참여자'),'rank':place,'points':points,'carbonKg':0,'isMe':key==user['user_id']})
        return result
    departments={};labels={}
    for uid,amount in totals.items():
        p=people.get(uid,{})
        if p.get('department_id'):
            key=p['department_id'];departments[key]=departments.get(key,0)+amount;labels[key]=p.get('department_name') or '등록 부서'
    return {'label':'캠페인 누적','personal':[{**r,'avatarDataUri':people.get(r['id'],{}).get('avatar_data_uri')} for r in rank(totals,{k:v.get('nickname') or '참여자' for k,v in people.items()})],
            'department':rank(departments,labels),'rewardPolicy':'누적 순위에 대한 추가 보상은 없습니다.'}
