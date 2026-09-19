import sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
from business import issue,mission_history,publish_rewards,weekly_outputs


def test_canonical_missions_idempotent(tmp_path):
    user={'user_id':'u','campaign_id':'c'}
    first=issue(tmp_path,user);second=issue(tmp_path,user)
    assert first['bundle_id']==second['bundle_id']
    assert first['missions']==second['missions']
    assert len(first['missions'])==4
    assert all(m['completion_rule']['target_count']==m['target_count'] for m in first['missions'])
    _,progress,responses=mission_history(tmp_path,[],[first])
    assert len(responses)==4 and not any(r['completed'] for r in responses)


def test_reward_retry_does_not_duplicate(tmp_path):
    row={'user_id':'u','campaign_id':'c','week':'2026-W37','payable':True,'points':15.0,'reason':'improved','policy_version':'reward-policy-v1'}
    first=publish_rewards(tmp_path,[row]);second=publish_rewards(tmp_path,[row,row])
    assert len(first)==len(second)==1
    assert first[0]['reward_id']==second[0]['reward_id']
    assert second[0]['points']==15


def test_final_projection_scopes_user_and_week():
    results={'weekly_gold':[{'campaign_id':'c','user_id':'u','week':'2026-W37'}],
        'baseline_gold':[], 'weekly_user_profile':[], 'next_week_missions':[],
        'ranking':[{'campaign_id':'other','user_id':'u','week':'2026-W37'}, {'campaign_id':'c','user_id':'different','week':'2026-W37'}],
        'campaign_kpi':[]}
    assert weekly_outputs(results)[0]['ranking']==[]


def test_real_model_distance_and_labels():
    from model import LocalModel,distance
    model=LocalModel();now=datetime.now(timezone.utc)
    points=[{'event_time':(now+timedelta(seconds=i)).isoformat(),'lat':37.5+i*.00001,'lon':127,'label':'car'} for i in range(42)]
    result=model.result({'trip_id':'distance-check'},points)
    assert result['model_version'].startswith('local-speedtransformer')
    assert sum(s['distance_m'] for s in result['segments'])==pytest.approx(sum(distance(a,b) for a,b in zip(points,points[1:])))
    before=[(s['mode'],s['confidence']) for s in result['segments']]
    for p in points:p['label']='walk'
    assert before==[(s['mode'],s['confidence']) for s in model.result({'trip_id':'distance-check'},points)['segments']]
    with pytest.raises(ValueError):model.result({'trip_id':'one-point'},points[:1])
