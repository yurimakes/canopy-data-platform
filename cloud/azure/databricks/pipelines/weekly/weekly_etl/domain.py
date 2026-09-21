"""Pure per-campaign mission/effective-baseline transformation for Lakeflow workers."""
import json
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
import pandas as pd
from downstream_bootstrap import activate

PACKET_SCHEMA='artifact string,campaign_id string,user_id string,week string,document_json string'


def campaign_domain(frame):
    activate()
    from business import mission_history, issue
    from build_mission_profile import build_profile_from_weekly_summary, _gold_profile, _responses_to_bundles
    from reward_baselines import publish_completed_weeks
    from services.weekly_cosmos import json_value
    inputs={}
    for row in frame.itertuples(index=False):
        inputs.setdefault(row.artifact,[]).append(json.loads(row.document_json))
    at=inputs['snapshot'][0]['created_at']
    with TemporaryDirectory() as folder:
        _,progress,responses=mission_history(folder,inputs.get('trips',[]),inputs.get('mission_bundles',[]),inputs.get('mission_events',[]))
        profiles=[];bundles=[]
        for row in inputs.get('weekly_gold',[]):
            start=datetime.strptime(row['week']+'-1','%G-W%V-%u').date()
            history=[r for r in responses if r['user_id']==row['user_id'] and r['campaign_id']==row['campaign_id'] and r['week_start']<=str(start)]
            profile=_gold_profile(build_profile_from_weekly_summary(row,user_id=row['user_id'],campaign_id=row['campaign_id'],source_week_start=str(start),source_week_end=str(start+timedelta(days=7)),bundle_history=_responses_to_bundles(history),mission_history_source='mission_response_weekly'))
            profiles.append(profile)
            bundles.append(issue(folder,profile,datetime.fromisoformat(profile['effective_week_start']).date(),[profile],persist=False))
        effective=publish_completed_weeks(folder,inputs.get('commute_weekly_gold',[]),inputs.get('users',[]),True,at=at,persist=False)
    outputs={'mission_progress':progress,'mission_response_weekly':responses,'weekly_user_profile':profiles,'next_week_missions':bundles,'effective_personal_baseline':effective}
    records=[]
    for name,rows in outputs.items():
        for row in json_value(rows):
            records.append((name,row.get('campaign_id'),row.get('user_id'),str(row.get('week') or row.get('week_start') or ''),json.dumps(row,allow_nan=False,default=str)))
    return pd.DataFrame(records,columns=['artifact','campaign_id','user_id','week','document_json'])


def final_rankings(frame):
    activate()
    from weekly_ledger import finalize_rankings
    from reward_baselines import week_of
    inputs={}
    for row in frame.itertuples(index=False):inputs.setdefault(row.artifact,[]).append(json.loads(row.document_json))
    rows=finalize_rankings(inputs.get('previous_ranking',[]),inputs.get('ranking_raw',[]),week_of(inputs['snapshot'][0]['created_at']))
    return pd.DataFrame([(json.dumps(r,default=str),) for r in rows],columns=['document_json'])


def combined_outputs(frame):
    activate()
    from business import weekly_outputs
    from services.weekly_cosmos import json_value
    inputs={k:[] for k in ['weekly_gold','baseline_gold','weekly_user_profile','next_week_missions','ranking','campaign_kpi']}
    for row in frame.itertuples(index=False):inputs.setdefault(row.artifact,[]).append(json.loads(row.document_json))
    return pd.DataFrame([(json.dumps(r,default=str,allow_nan=False),) for r in json_value(weekly_outputs(inputs))],columns=['document_json'])


def _frame(rows):
    return pd.DataFrame([r.asDict() if hasattr(r,'asDict') else dict(r) for r in rows],columns=['artifact','campaign_id','document_json'])


def campaign_rows(rows):
    return campaign_domain(_frame(rows)).to_dict('records')


def ranking_rows(rows):
    return final_rankings(_frame(rows)).to_dict('records')


def combined_rows(rows):
    return combined_outputs(_frame(rows)).to_dict('records')


def behavior_rows(rows):
    activate()
    from build_behavior_change import _compute_rolling_for_user, BEHAVIOR_CHANGE_POLICY
    from services.weekly_cosmos import json_value
    policy=BEHAVIOR_CHANGE_POLICY
    frame=pd.DataFrame([r.asDict() if hasattr(r,'asDict') else dict(r) for r in rows])
    return json_value(_compute_rolling_for_user(frame,policy['before_period_weeks'],policy['after_period_weeks'],policy['minimum_delta'],policy['policy_version']).to_dict('records'))
