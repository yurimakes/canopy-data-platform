import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/local'),str(ROOT/'apps/api')]
from journey_rewards import route_quote, test_quote as fixture_quote, prepare, bind, settle, store
from rewards import ledger, extension_policy, acknowledge_mission, settle_ranking, bonus_wallet
from services.trip_service import ApiError
from services.reward_rules import journey_points

USER={'user_id':'owner','campaign_id':'test'}


def prepared(tmp_path):
    quote=fixture_quote(tmp_path,USER,None)
    prepare(tmp_path,USER,quote['quoteId']);bind(tmp_path,USER,'trip')
    now=datetime.now(timezone.utc)
    trip={**USER,'trip_id':'trip','status':'ready','started_at':now.isoformat(),
          'ended_at':(now+timedelta(minutes=25)).isoformat(),'confirmed_trip':{'total_carbon_kg':0.01}}
    points=[{'lat':37.5,'lon':127,'event_time':trip['started_at']},
            {'lat':37.518,'lon':127,'event_time':trip['ended_at']}]
    return trip,points


def test_trip_reward_concurrent_retry_and_timezone(tmp_path):
    trip,points=prepared(tmp_path)
    points[-1]['event_time']=datetime.fromisoformat(points[-1]['event_time']).astimezone(timezone(timedelta(hours=9))).isoformat()
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows=list(pool.map(lambda _:settle(tmp_path,USER,trip,points),range(10)))
    assert all(r['status']=='paid' and r['points']==30 for r in rows)
    assert len(ledger(tmp_path).all())==1
    assert bonus_wallet(tmp_path,USER,{'state':'empty'})['data']['balance']==30
    assert bonus_wallet(tmp_path,{'user_id':'other','campaign_id':'test'},{'state':'empty'})['data']['balance']==0


def test_trip_endpoint_and_no_route(tmp_path):
    trip,points=prepared(tmp_path)
    points[-1]['lat']=37.501
    assert settle(tmp_path,USER,trip,points)['status']=='route_incomplete'
    assert ledger(tmp_path).all()==[]
    assert settle(tmp_path,USER,{**trip,'trip_id':'free'},points)['status']=='no_route'


def test_quote_ownership_expiry_and_snapshot(tmp_path):
    quote=fixture_quote(tmp_path,USER,None)
    with pytest.raises(ApiError):prepare(tmp_path,{'user_id':'other','campaign_id':'test'},quote['id'])
    prepare(tmp_path,USER,quote['id']);bind(tmp_path,USER,'trip')
    old=store(tmp_path).read_item(quote['id'])
    store(tmp_path).replace_item(quote['id'],{**old,'expected_kg':99,'expires_at':'2000-01-01T00:00:00+00:00'},etag=old['_etag'])
    assert store(tmp_path).read_item('trip:trip')['quote']['expected_kg']!=99
    with pytest.raises(ApiError):prepare(tmp_path,USER,quote['id'])


def test_zero_negative_and_small_savings():
    policy=extension_policy()
    assert journey_points(.1,.2,policy)==(0,0)
    assert journey_points(.1,.099,policy)==(.001,0)
    with pytest.raises(ValueError):journey_points(float('nan'),0,policy)


def test_mission_claim_requires_completion_and_is_once(tmp_path,monkeypatch):
    import rewards
    mission={'assignment_id':'a','mission_name':'걷기','completed':False}
    monkeypatch.setattr(rewards,'current_missions',lambda *args:{'missions':[mission],'week_start':'2026-09-14'})
    with pytest.raises(ApiError):acknowledge_mission(tmp_path,USER,'a',[])
    with pytest.raises(ApiError):acknowledge_mission(tmp_path,USER,'unknown',[])
    mission['completed']=True
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows=list(pool.map(lambda _:acknowledge_mission(tmp_path,USER,'a',[]),range(10)))
    assert all(r['points']==10 for r in rows)
    assert len(ledger(tmp_path).all())==1


def test_ranking_only_closed_successful_week(tmp_path):
    folder=tmp_path/'weekly';folder.mkdir()
    (folder/'ranking.json').write_text(json.dumps([{**USER,'ranking_type':'personal','week':'2020-W01','rank':1},
         {**USER,'ranking_type':'personal','week':'2099-W01','rank':1}]))
    (folder/'run.json').write_text(json.dumps({'stages':{'ranking':{'status':'failed'}}}))
    settle_ranking(tmp_path);assert ledger(tmp_path).all()==[]
    (folder/'run.json').write_text(json.dumps({'stages':{'ranking':{'status':'passed'}}}))
    settle_ranking(tmp_path);settle_ranking(tmp_path)
    assert len(ledger(tmp_path).all())==1
    assert ledger(tmp_path).all()[0]['points']==100


def test_real_ktdb_quote(tmp_path):
    quote=route_quote(tmp_path,USER,{'name':'A','latitude':37.5,'longitude':127},
                      {'name':'B','latitude':37.518,'longitude':127})
    record=store(tmp_path).read_item(quote['id'])
    assert record['model_version'].startswith('ktdb-population-')
    assert sum(record['probabilities'].values())==pytest.approx(1)
    assert len(record['features'])==19
    assert 0<quote['expectedKg']<1
    assert 'fixture' not in record['model_version']
