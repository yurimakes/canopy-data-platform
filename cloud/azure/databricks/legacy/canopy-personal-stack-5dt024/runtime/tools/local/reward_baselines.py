"""Immutable local reward-week contexts. No Azure access; reuse team eligibility/math."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import math
from business import read_rows
from rewards import identity, extension_policy
from services.local_documents import LocalDocuments
from azure.cosmos.exceptions import CosmosResourceNotFoundError, CosmosResourceExistsError
from weekly_publication import consistent_read


def week_of(at=None):
    instant=datetime.fromisoformat(at.replace('Z','+00:00')) if isinstance(at,str) else at or datetime.now(timezone.utc)
    if instant.tzinfo is None:raise ValueError('timezone required')
    return instant.astimezone(ZoneInfo('Asia/Seoul')).strftime('%G-W%V')


def snapshots(data):return LocalDocuments(Path(data)/'reward-baselines.sqlite')


def save_once(data,user,week,personal=None,global_row=None,persist=True):
    key=identity('reward-baseline',user,week);db=snapshots(data)
    def value(row):
        x=(row or {}).get('baseline_g_co2e_per_km')
        return float(x) if row and row.get('status')=='ready' and isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) and x>=0 else None
    row={'id':key,'user_id':user['user_id'],'campaign_id':user['campaign_id'],'week':week,
         'personal':value(personal),'global':value(global_row),'personal_snapshot':personal,'global_snapshot':global_row,
         'settlement_version':'local-trip-settlement-v2','policy':extension_policy(),'created_at':datetime.now(timezone.utc).isoformat()}
    if not persist:return {**row,'publication_status':'pending'}
    row['publication_status']='published'
    try:return db.create_item(row)
    except CosmosResourceExistsError:
        old=db.read_item(key)
        # Upgrade only legacy placeholders created before any publication.
        # Already bound Trip copies and actual published collecting rows stay fixed.
        if not old.get('publication_status') and old.get('personal_snapshot') is None and old.get('global_snapshot') is None and (personal is not None or global_row is not None):
            from azure.cosmos.exceptions import CosmosHttpResponseError
            try:return db.replace_item(key,row,etag=old['_etag'])
            except CosmosHttpResponseError as exc:
                if exc.status_code!=412:raise
                return db.read_item(key)
        return old


@consistent_read
def freeze(data,user,at=None):
    week=week_of(at)
    old=None
    try:
        old=snapshots(data).read_item(identity('reward-baseline',user,week))
        if old.get('publication_status') or old.get('personal_snapshot') is not None or old.get('global_snapshot') is not None:return old
    except CosmosResourceNotFoundError:pass
    # Do not silently relabel an older week's baseline as this week's baseline.
    candidates=read_rows(Path(data)/'weekly/effective_personal_baseline.json')+read_rows(Path(data)/'weekly/personal_baseline.json')
    personal=next((r for r in candidates if r.get('week')==week and r.get('user_id')==user['user_id'] and r.get('campaign_id')==user['campaign_id']),None)
    global_row=next((r for r in read_rows(Path(data)/'weekly/global_baseline.json') if r.get('week')==week and r.get('campaign_id')==user['campaign_id']),None)
    global_row=(personal or {}).get('_global_snapshot') or global_row
    # A Trip keeps its own immutable copy of this fallback. A read before the
    # publisher runs must not create a permanent empty weekly publication.
    if old is not None and personal is None and global_row is None:return old
    return save_once(data,user,week,personal,global_row,persist=personal is not None or global_row is not None)


def publish_completed_weeks(data,weekly,users,commute_verified=False,at=None,persist=True):
    """Add an evaluation row even before the user's first Trip of the new week."""
    import pandas as pd
    from build_personal_baseline import _compute_personal_baseline
    from baseline_eligibility import load_eligibility_policy,evaluate_global_eligibility
    policy=load_eligibility_policy();current=week_of(at);result=[]
    scopes={(r['campaign_id'],r['user_id']) for r in weekly}
    for campaign,user_id in scopes:
        history=[dict(r) for r in weekly if r['campaign_id']==campaign and r['user_id']==user_id and r['week']<current]
        if not history:continue
        # Current evaluation week has zero contribution, and the canonical shift excludes it.
        history.append({'campaign_id':campaign,'user_id':user_id,'week':current,'trip_count':0,'total_kg_co2e':0.,'total_distance_m':0.})
        calculated=_compute_personal_baseline(pd.DataFrame(history),'baseline-policy-v4',eligibility_policy=policy,
            identities={'users':users,'memberships':[]},commute_scope_verified=commute_verified)
        rows=calculated.to_dict('records') if hasattr(calculated,'to_dict') else calculated
        result.extend(r for r in rows if r['week']==current)
    for p in result:
        ready=[r for r in result if r['campaign_id']==p['campaign_id'] and r['status']=='ready']
        gate=evaluate_global_eligibility(len(ready),policy)
        g={'campaign_id':p['campaign_id'],'week':current,**gate,'policy_version':'baseline-policy-v4',
           'baseline_g_co2e_per_km':sum(r['baseline_g_co2e_per_km'] for r in ready)/len(ready) if gate['status']=='ready' else None}
        p['_global_snapshot']=g
        if persist:save_once(data,p,current,p,g)
    return result


def paid_trip_history(data):
    from rewards import ledger
    mocks={t['trip_id'] for t in read_rows(Path(data)/'inputs/trips.json') if t.get('is_mock') or (t.get('start_context') or {}).get('simulation')}
    rows=[]
    for r in ledger(data).all():
        if r.get('kind')!='trip' or r.get('status')!='paid' or r.get('trip_id') in mocks:continue
        week=r.get('week') or week_of(r['created_at'])
        start=datetime.strptime(week+'-1','%G-W%V-%u').date().isoformat()
        rows.append({'id':r['id'],'reward_id':r['id'],'trip_id':r['trip_id'],'user_id':r['user_id'],'campaign_id':r['campaign_id'],
            'week':start,'week_label':week,'points':r['points'],'status':'paid','label':r['title'],'occurred_at':r['created_at'],'policy_version':r['policy_version']})
    return rows
