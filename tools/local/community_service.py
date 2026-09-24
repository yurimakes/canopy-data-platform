"""The same community projection for local and hosted storage adapters."""
from datetime import datetime,timezone
from weekly_publication import consistent_read

@consistent_read
def view(data,user,trips):
    from projections import community,mission_panel
    from business import owned_missions,visible_missions
    from rewards import acknowledged,baseline,settle_ranking,bonus_wallet
    from activity import notifications
    result=community(data,user)
    result['missions']=mission_panel(visible_missions(owned_missions(data,user,trips)),acknowledged(data,user))
    b=baseline(data,user) or {}
    ready=b.get('status')=='ready'
    result['baseline']={'state':'ready','data':{'week':b.get('week'),'status':b.get('status','collecting'),
        'personalKg':b.get('baseline_g_co2e_per_km') if ready else None,
        'globalKg':b.get('global_baseline_g_co2e_per_km'),'unit':'gCO₂e/km',
        'updatedAt':datetime.now(timezone.utc).isoformat(),'reason':'개인 이동 기준 준비 완료' if ready else '유효한 여정과 관찰 기간이 쌓이면 주간 집계에서 개인 기준을 만들어요.',
        'eligibilityReason':b.get('eligibility_reason'),'policyVersion':b.get('policy_version'),
        'developmentOnly':b.get('development_only',False),'trips':b.get('confirmed_trip_count',0),
        'observationDays':b.get('observation_days',0),'source':b.get('source','Weekly 개인 기준')}}
    settle_ranking(data)
    result['rewards']=bonus_wallet(data,user,result['rewards'])
    result['notifications']=notifications(data,user,trips,result['missions'],result['rewards'])
    return result
