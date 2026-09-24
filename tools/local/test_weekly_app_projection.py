import json,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/local'),str(ROOT/'apps/api')]
from reward_baselines import freeze,week_of
from rewards import baseline,settle_ranking,ledger

def test_new_member_sees_global_without_personal_history(tmp_path):
 folder=tmp_path/'weekly';folder.mkdir()
 week=week_of();other={'user_id':'other','campaign_id':'campaign','week':week,'status':'ready','baseline_g_co2e_per_km':80.,'_global_snapshot':{'campaign_id':'campaign','week':week,'status':'ready','baseline_g_co2e_per_km':95.}}
 (folder/'effective_personal_baseline.json').write_text(json.dumps([other]))
 user={'user_id':'new','campaign_id':'campaign'}
 result=baseline(tmp_path,user)
 assert result['status']=='collecting'
 assert result['baseline_g_co2e_per_km'] is None
 assert result['global_baseline_g_co2e_per_km']==95.
 unrelated=freeze(tmp_path,{'user_id':'new','campaign_id':'other-campaign'})
 assert unrelated['global'] is None

def test_synthetic_ranking_does_not_credit_wallet(tmp_path):
 folder=tmp_path/'weekly';folder.mkdir()
 (folder/'run.json').write_text(json.dumps({'synthetic':True,'stages':{'ranking':{'status':'passed'}}}))
 (folder/'ranking.json').write_text(json.dumps([{'user_id':'test','campaign_id':'campaign','week':'2020-W01','ranking_type':'personal','rank':1}]))
 settle_ranking(tmp_path)
 assert ledger(tmp_path).all()==[]

def test_synthetic_cumulative_ranking_uses_published_ledger_only(tmp_path):
 from activity import cumulative_ranking
 folder=tmp_path/'weekly';folder.mkdir()
 (folder/'run.json').write_text(json.dumps({'synthetic':True}))
 (folder/'reward_ledger.json').write_text(json.dumps([
  {'user_id':'test','campaign_id':'campaign','points':10},
  {'user_id':'test','campaign_id':'campaign','points':20},
  {'user_id':'foreign','campaign_id':'other','points':999}]))
 user={'user_id':'test','campaign_id':'campaign','nickname':'Tester'}
 result=cumulative_ranking(tmp_path,user,[user])
 assert len(result['personal'])==1
 assert result['personal'][0]['points']==30
 assert ledger(tmp_path).all()==[]
