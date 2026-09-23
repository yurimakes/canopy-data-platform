"""Strict input boundary: rankings summarize paid Trips, never create payments."""
import math
def validate_paid_ledger(rows):
    seen={};trips={}
    for row in rows:
        if row.get('status')!='paid':continue
        if not all(isinstance(row.get(k),str) and row[k] for k in ('reward_id','trip_id','user_id','campaign_id','week','week_label')):raise ValueError('paid Trip ledger identity missing')
        points=row.get('points')
        if isinstance(points,bool) or not isinstance(points,(int,float)) or not math.isfinite(points) or points<0:raise ValueError('invalid paid points')
        key=row['reward_id'];trip=(row['campaign_id'],row['user_id'],row['trip_id'])
        if key in seen and seen[key]!=row:raise ValueError('conflicting reward identity')
        if trip in trips and trips[trip]!=key:raise ValueError('Trip paid more than once')
        seen[key]=row;trips[trip]=key
    return list(seen.values())

def finalize_rankings(previous,current,week):
    """Do not rewrite a previously published closed-week ranking."""
    frozen={(r['campaign_id'],r['week']) for r in previous if r.get('confirmed') is True and r['week']<week}
    return ([r for r in previous if (r['campaign_id'],r['week']) in frozen]+
        [{**r,'confirmed':r['week']<week} for r in current if (r['campaign_id'],r['week']) not in frozen])
