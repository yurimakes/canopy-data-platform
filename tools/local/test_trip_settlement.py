from datetime import datetime,timezone,timedelta
import json
import sys
from pathlib import Path
import pytest
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[2]/'apps/api')]
from test_rewards import USER,prepared
from reward_baselines import save_once,freeze,week_of,publish_completed_weeks,paid_trip_history,snapshots
from journey_rewards import settle
from rewards import ledger,identity
from business import LedgerStore


def baseline(value):return {**USER,'status':'ready','baseline_g_co2e_per_km':value,'policy_version':'test-baseline'}


@pytest.mark.parametrize('personal,global_value,actual,classification,points',[(100,80,.04,'improved',16),(20,80,.06,'maintained',10),(20,30,.1,'no_change',0)])
def test_trip_evaluated_against_weekly_context(tmp_path,personal,global_value,actual,classification,points):
    save_once(tmp_path,USER,week_of(),baseline(personal),baseline(global_value))
    trip,gps=prepared(tmp_path);trip['confirmed_trip']['total_carbon_kg']=actual
    result=settle(tmp_path,USER,trip,gps)
    assert result['points']==points and result['classification']==classification
    assert result['baseline_week']==week_of(trip['started_at'])
    with pytest.raises(Exception):settle(tmp_path,{**USER,'user_id':'another'},trip,gps)


def test_week_context_cannot_change_and_next_week_is_independent(tmp_path):
    first=save_once(tmp_path,USER,'2026-W38',baseline(100),baseline(80))
    assert save_once(tmp_path,USER,'2026-W38',baseline(1),baseline(2))['id']==first['id']
    assert freeze(tmp_path,USER,'2026-09-20T14:59:00Z')['personal']==100
    next_week=freeze(tmp_path,USER,'2026-09-20T15:00:00Z')
    assert next_week['week']=='2026-W39' and next_week['personal'] is None


def test_two_trips_paid_once_each_and_rank_input_excludes_other_awards(tmp_path):
    trip,gps=prepared(tmp_path)
    first=settle(tmp_path,USER,trip,gps)
    from journey_rewards import bind
    bind(tmp_path,USER,'second')
    second=settle(tmp_path,USER,{**trip,'trip_id':'second'},gps)
    ledger(tmp_path).create_item({'id':'mission','kind':'mission','status':'paid','points':999})
    rows=paid_trip_history(tmp_path)
    assert len(rows)==2 and sum(r['points'] for r in rows)==first['points']+second['points']
    assert {r['trip_id'] for r in rows}=={'trip','second'}


def test_closed_history_creates_new_week_without_new_trip(tmp_path):
    users=[{**USER,'campaign_joined_at':'2026-08-01T00:00:00Z'}]
    rows=[{**USER,'week':'2026-W37','trip_count':6,'total_distance_m':10000.,'total_kg_co2e':1.},
          {**USER,'week':'2026-W38','trip_count':6,'total_distance_m':10000.,'total_kg_co2e':99.}]
    result=publish_completed_weeks(tmp_path,rows,users,True,datetime(2026,9,14,tzinfo=timezone.utc))
    assert len(result)==1 and result[0]['baseline_g_co2e_per_km']==100
    assert freeze(tmp_path,USER,'2026-09-14T01:00:00Z')['personal']==100
    publish_completed_weeks(tmp_path,rows,users,True,datetime(2026,9,21,tzinfo=timezone.utc))
    assert freeze(tmp_path,USER,'2026-09-21T01:00:00Z')['personal']==5000
    assert freeze(tmp_path,USER,'2026-09-14T01:00:00Z')['personal']==100


def test_legacy_weekly_payment_not_paid_twice(tmp_path):
    trip,gps=prepared(tmp_path)
    LedgerStore(tmp_path/'rewards.sqlite').create_item({**USER,'id':'old','week':week_of(trip['started_at']),'status':'paid','points':20})
    assert settle(tmp_path,USER,trip,gps)['status']=='legacy_weekly_paid'
    assert ledger(tmp_path).all()==[]


@pytest.mark.parametrize('offset,expected',[(.109,'paid'),(1.001,'insufficient_gps')])
def test_ktdb_endpoint_clock_skew_matches_finalizer(tmp_path,offset,expected):
    trip,gps=prepared(tmp_path)
    gps[0]['event_time']=(datetime.fromisoformat(trip['started_at'].replace('Z','+00:00'))-timedelta(seconds=offset)).isoformat()
    assert settle(tmp_path,USER,trip,gps)['status']==expected
