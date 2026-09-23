"""검증된 6명 시나리오 조회. 실제 로그인 계정의 여정과 원장은 변경하지 않음."""
import json
from decimal import Decimal
from pathlib import Path
from business import read_rows
from projections import community,reward_title
from rewards import settle_ranking,ledger


def panels():
    root=Path(__file__).resolve().parents[2]/'.local-data/scenarios/baseline'
    run=read_rows(root/'weekly/run.json') or {}
    if not run.get('stages') or any(s['status']!='passed' for s in run['stages'].values()):
        raise ValueError('통합 시나리오 검증을 먼저 실행해주세요.')
    users=read_rows(root/'inputs/users.json')
    user=users[0]
    result=community(root,user)
    result['baseline']['data'].update(developmentOnly=True,source='6명 합성 여정의 실제 Weekly 계산 결과')
    # 정산 결과와 동일한 파일을 표시하며 별도 지급은 시나리오 저장소에만 반영
    settle_ranking(root)
    weekly=[r for r in read_rows(root/'weekly/reward_ledger.json') if r['user_id']==user['user_id'] and r['campaign_id']==user['campaign_id'] and r.get('status') in ('paid','adjusted')]
    rank=[r for r in ledger(root).all() if r['user_id']==user['user_id'] and r['campaign_id']==user['campaign_id'] and r['status']=='paid']
    items=[{'id':r['reward_id'],'title':reward_title(r),'time':r['occurred_at'],'amount':r['points'],'status':'paid','kind':'weekly'} for r in weekly]
    items += [{'id':r['id'],'title':r['title'],'time':r['created_at'],'amount':r['points'],'status':'paid','kind':'ranking'} for r in rank]
    result['rewards']={'state':'ready','data':{'balance':float(sum(Decimal(str(r['amount'])) for r in items)),'items':items,'developmentOnly':True}}
    names={u['user_id']:u['nickname'] for u in users}
    if result['ranking']['state']=='ready':
        for r in result['ranking']['data']['personal']:r['name']=names.get(r['id'],r['name'])
    return {**result,'user':user['nickname'],'inputTrips':run['input_trips'],'stages':run['stages']}
