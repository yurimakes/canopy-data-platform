"""로컬 주간 결과를 앱 표시 모델로 변환. 집계 수치 재계산 제외."""
import json
from datetime import datetime, timezone


def reward_title(row):
    label=row.get('label','')
    if row.get('status')=='adjusted':return '주간 보상 조정'
    if 'personal_baseline' in label:return '주간 탄소 개선 보상'
    if 'global_baseline' in label:return '주간 탄소 유지 보상'
    return '주간 탄소 절감 보상'


def community(data, user):
    from rewards import extension_policy
    folder=data/'weekly'
    from weekly_publication import resolve
    def rows(name):
        return __import__('business').read_rows(folder/(name+'.json'))
    def owned(records):
        return [r for r in records if r.get('campaign_id')==user['campaign_id'] and r.get('user_id')==user['user_id']]
    run_path=resolve(folder/'run.json')
    now=datetime.fromtimestamp(run_path.stat().st_mtime,timezone.utc).isoformat() if run_path.exists() else datetime.now(timezone.utc).isoformat()
    run=__import__('business').read_rows(folder/'run.json') or {}
    empty={'state':'empty'}
    result={key:empty for key in ('baseline','missions','ranking','rewards')}
    personal=sorted(owned(rows('personal_baseline')),key=lambda r:r.get('week',''))
    if personal:
        p=personal[-1]
        global_rows=[g for g in rows('global_baseline') if g.get('campaign_id')==user['campaign_id'] and g.get('week')==p['week']]
        g=global_rows[-1] if global_rows else {}
        result['baseline']={'state':'ready','data':{'status':'ready' if p.get('status')=='ready' else 'collecting','updatedAt':now,
            'personalKg':p.get('baseline_g_co2e_per_km'),'globalKg':g.get('baseline_g_co2e_per_km'),
            'unit':'gCO₂e/km','week':p['week'],'reason':'개인 기준 준비 완료' if p.get('status')=='ready' else '관찰 기간 또는 유효한 여정이 부족해요.'}}
        weekly=[r for r in owned(rows('weekly_gold')) if r.get('week')==p['week']]
        if weekly and weekly[-1]['total_distance_m']>0:
            result['baseline']['data']['actualG']=weekly[-1]['total_kg_co2e']*1000000/weekly[-1]['total_distance_m']
    bundles=sorted(owned(rows('next_week_missions')),key=lambda r:r.get('week_start',''))
    if bundles:
        b=bundles[-1]
        result['missions']={'state':'ready','data':{'week':b.get('week_start',''),'updatedAt':now,'items':[
            {'id':m['assignment_id'],'title':m.get('mission_name','미션'),'category':m.get('category_label',''),
             'description':m.get('mission_description',''),'progress':m.get('progress_count',0),
             'goal':m.get('target_count',0),'unit':m.get('progress_unit','회'),
             'status':'completed' if m.get('completed') else 'active'} for m in b.get('missions',[])]}}
    users=__import__('business').read_rows(data/'inputs/users.json')
    people={u['user_id']:u for u in users if u.get('campaign_id')==user['campaign_id']}
    departments={u['department_id']:u.get('department_name') or '등록 부서' for u in people.values() if u.get('department_id')}
    rankings=[r for r in rows('ranking') if r.get('campaign_id')==user['campaign_id']]
    if rankings:
        week=max(r['week'] for r in rankings)
        def mapped(kind):
            return [{'id':r.get('user_id') or r.get('department_id'),'name':(people.get(r.get('user_id'),{}).get('nickname') or '참여자') if kind=='personal' else departments.get(r.get('department_id'),'등록 부서'),
                'avatarDataUri':people.get(r.get('user_id'),{}).get('avatar_data_uri') if kind=='personal' else None,'rank':r['rank'],'carbonKg':0,'points':r['reward_points'],'isMe':r.get('user_id')==user['user_id']}
                for r in rankings if r['week']==week and r['ranking_type']==kind]
        result['ranking']={'state':'ready','data':{'week':week,'updatedAt':now,'personal':mapped('personal'),'department':mapped('department'),'awards':extension_policy()['rank_awards']}}
    ledger_path=data/'inputs/reward_ledger_history.json'
    ledger=owned(__import__('business').read_rows(ledger_path))
    if ledger:
        paid=[r for r in ledger if r.get('status') in ('paid','adjusted')]
        result['rewards']={'state':'ready','data':{'balance':sum(r.get('points',0) for r in paid),'items':[
            {'id':r['reward_id'],'title':reward_title(r),'time':r.get('occurred_at',now),'amount':r.get('points',0),
            'kind':'weekly','status':'paid' if r.get('status') in ('paid','adjusted') else 'pending'} for r in ledger]}}
    for panel,stage in [('baseline','personal_baseline'),('missions','next_week_missions'),('ranking','ranking')]:
        state=run.get('stages',{}).get(stage,{})
        if state.get('status')=='failed':result[panel]={'state':'error','message':'로컬 계산 실패: '+state.get('error','')[:250]}
    from activity import cumulative_ranking
    cumulative=cumulative_ranking(data,user,users)
    if result['ranking']['state']!='ready':result['ranking']={'state':'ready','data':{'week':datetime.now().strftime('%G-W%V'),'updatedAt':now,'personal':[],'department':[],'awards':extension_policy()['rank_awards']}}
    result['ranking']['data']['cumulative']=cumulative
    attempt=__import__('business').read_rows(folder/'last-attempt.json') or {}
    def instant(value):return datetime.fromisoformat(value.replace('Z','+00:00')) if value else datetime.min.replace(tzinfo=timezone.utc)
    if instant(attempt.get('completed_at'))>instant(run.get('completed_at')):
        result['weeklyStatus']={'state':'error','message':'최근 주간 집계를 완료하지 못했어요. 마지막 정상 결과를 표시하고 있습니다.'}
    return result


def mission_panel(bundle,acknowledged=None):
    from rewards import extension_policy
    reward=extension_policy()['mission_tokens']
    return {'state':'ready','data':{'week':bundle['week_start'],'updatedAt':bundle.get('created_at'),'items':[
        {'id':m['assignment_id'],'title':m['mission_name'],'category':m['category_label'],'description':m['mission_description'],
         'week':m.get('week_start',bundle['week_start']),'rewardPoints':reward,'progress':m.get('progress_count',0),'goal':m['target_count'],'unit':m['progress_unit'],
         'status':('completed' if m['assignment_id'] in (acknowledged or set()) else 'claimable') if m.get('completed') else 'active'} for m in bundle['missions']]}}
