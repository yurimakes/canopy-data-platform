"""로컬 주간 결과를 앱 표시 모델로 변환. 집계 수치 재계산 제외."""
import json
from datetime import datetime, timezone


def community(data, user):
    folder=data/'weekly'
    def rows(name):
        path=folder/(name+'.json')
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    def owned(records):
        return [r for r in records if r.get('campaign_id')==user['campaign_id'] and r.get('user_id')==user['user_id']]
    run_path=folder/'run.json'
    now=datetime.fromtimestamp(run_path.stat().st_mtime,timezone.utc).isoformat() if run_path.exists() else datetime.now(timezone.utc).isoformat()
    run=json.loads(run_path.read_text(encoding='utf-8')) if run_path.exists() else {}
    empty={'state':'empty'}
    result={key:empty for key in ('baseline','missions','ranking','rewards')}
    personal=sorted(owned(rows('personal_baseline')),key=lambda r:r.get('week',''))
    if personal:
        p=personal[-1]
        global_rows=[g for g in rows('global_baseline') if g.get('campaign_id')==user['campaign_id'] and g.get('week')==p['week']]
        g=global_rows[-1] if global_rows else {}
        result['baseline']={'state':'ready','data':{'status':'ready' if p.get('status')=='ready' else 'collecting','updatedAt':now,
            'personalKg':p.get('baseline_g_co2e_per_km'),'globalKg':g.get('baseline_g_co2e_per_km'),
            'unit':'gCO₂e/km','reason':p.get('eligibility_reason') or str(p.get('status','collecting'))}}
    bundles=sorted(owned(rows('next_week_missions')),key=lambda r:r.get('week_start',''))
    if bundles:
        b=bundles[-1]
        result['missions']={'state':'ready','data':{'week':b.get('week_start',''),'updatedAt':now,'items':[
            {'id':m['assignment_id'],'title':m.get('mission_name','미션'),'category':m.get('category_label',''),
             'description':m.get('mission_description',''),'progress':m.get('progress_count',0),
             'goal':m.get('target_count',0),'unit':m.get('progress_unit','회'),
             'status':'completed' if m.get('completed') else 'active'} for m in b.get('missions',[])]}}
    rankings=[r for r in rows('ranking') if r.get('campaign_id')==user['campaign_id']]
    if rankings:
        week=max(r['week'] for r in rankings)
        def mapped(kind):
            return [{'id':r.get('user_id') or r.get('department_id'),'name':r.get('user_id') or r.get('department_id'),
                'rank':r['rank'],'carbonKg':0,'points':r['reward_points'],'isMe':r.get('user_id')==user['user_id']}
                for r in rankings if r['week']==week and r['ranking_type']==kind]
        result['ranking']={'state':'ready','data':{'week':week,'updatedAt':now,'personal':mapped('personal'),'department':mapped('department')}}
    ledger_path=data/'inputs/reward_ledger_history.json'
    ledger=owned(json.loads(ledger_path.read_text(encoding='utf-8'))) if ledger_path.exists() else []
    if ledger:
        paid=[r for r in ledger if r.get('status') in ('paid','adjusted')]
        result['rewards']={'state':'ready','data':{'balance':sum(r.get('points',0) for r in paid),'items':[
            {'id':r['reward_id'],'title':r.get('reason','주간 보상'),'time':r.get('created_at',now),'amount':r.get('points',0),
            'status':'paid' if r.get('status') in ('paid','adjusted') else 'pending'} for r in ledger]}}
    for panel,stage in [('baseline','personal_baseline'),('missions','next_week_missions'),('ranking','ranking')]:
        state=run.get('stages',{}).get(stage,{})
        if state.get('status')=='failed':result[panel]={'state':'error','message':'로컬 계산 실패: '+state.get('error','')[:250]}
    return result
