import os,sys,unittest,random,json,hashlib
from pathlib import Path
from datetime import datetime,timedelta,timezone
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/"runtime/apps/api"),str(ROOT)]
os.environ['CANOPY_KTDB_REFERENCE_ROOT']=str(ROOT)
os.environ['CANOPY_TRANSIT_REFERENCE_DIR']=str(ROOT/'assets/transit')
from service.phone_model import PhoneModel,features,stamp
from service.run_trip import select_points
from service.isolation import require_table,TABLES
from src.aihub.features import canonical_window_features as original
from src.aihub.ingest import AiHubPoint
from services.trip_processor import validate_result
from services.trip_carbon import carbon_for

class IntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.model=PhoneModel()
 def points(self,n=241):
  t=datetime(2026,1,1,tzinfo=timezone.utc)
  return [{'user_id':'user','trip_id':'trip','sequence':i+1,'event_time':(t+timedelta(seconds=i)).isoformat(),'lat':37.55+i*.000008,'lon':126.99,'accuracy':5.,'altitude_m':10.} for i in range(n)]
 def trip(self,p):return {'trip_id':'trip','user_id':'user','campaign_id':'sandbox','started_at':p[0]['event_time'],'ended_at':p[-1]['event_time'],'expected_last_sequence':len(p)}
 def test_feature_and_probability_parity(self):
  rng=random.Random(20260924)
  for case in range(150):
   t=datetime(2026,1,1,tzinfo=timezone.utc);p=[]
   for i in range(rng.randint(2,150)):
    t+=timedelta(seconds=rng.choice([0,1,5,10,130]))
    p.append({'event_time':t.isoformat(),'lat':37.5+rng.random()*.002,'lon':127+rng.random()*.002,'accuracy':rng.choice([None,3.,15.]),'altitude_m':rng.choice([None,0.,25.])})
   before=original([AiHubPoint(timestamp=stamp(x['event_time']),latitude=x['lat'],longitude=x['lon'],accuracy_m=x['accuracy'],altitude_m=x['altitude_m']) for x in p],user_id='test',trajectory_id='test')
   after=features(p);cols=self.model.bundle['feature_columns']
   self.assertEqual(set(after),set(cols));self.assertEqual([before[k] for k in cols],[after[k] for k in cols])
   expected=self.model.bundle['model'].predict_proba(pd.DataFrame([before],columns=cols))[0]
   probs,_=self.model.predict_window(p);np.testing.assert_array_equal(expected,list(probs.values()))
 def test_transit_and_carbon(self):
  p=self.points();trip=self.trip(p);r=self.model.result(trip,p)
  self.assertTrue(r['segments']);self.assertEqual(len(r['transit_evidence']),12)
  self.assertEqual(r['data_quality']['status'],'complete');validate_result(trip,r)
  self.assertEqual(len(r['transit_evidence'][0]['reference']['files']),4)
  self.assertGreaterEqual(carbon_for(r['segments'],'mode').emission_kgco2e,0)
 def test_incomplete_tail(self):
  p=self.points(181);r=self.model.result(self.trip(p),p)
  self.assertEqual(r['data_quality']['status'],'complete');self.assertEqual(r['segments'][-1]['end_time'],p[-1]['event_time'])
 def test_short_trip_not_fabricated(self):
  p=self.points(45);r=self.model.result(self.trip(p),p)
  self.assertTrue(r['segments']);self.assertEqual(r['segments'][-1]['end_time'],p[-1]['event_time'])
 def test_sequence_completeness_and_conflicts(self):
  p=self.points();trip=self.trip(p)
  self.assertEqual(len(select_points(p+[p[0]],trip)),len(p))
  with self.assertRaises(ValueError):select_points(p[:-1],trip)
  with self.assertRaises(ValueError):select_points(p+[{**p[0],'lat':0}],trip)
  with self.assertRaises(ValueError):select_points([{**p[0],'user_id':'someone-else'}],trip)
 def test_gap_is_not_classified_as_motion(self):
  p=self.points(121);p.append({**p[-1],'sequence':122,'event_time':(stamp(p[-1]['event_time'])+timedelta(seconds=200)).isoformat()})
  r=self.model.result(self.trip(p),p);self.assertTrue(any(x['reason']=='collection_gap' for x in r['data_quality']['excluded_intervals']))
 def test_isolation(self):
  for role in TABLES:
   self.assertEqual(require_table(TABLES[role],role),TABLES[role])
   with self.assertRaises(ValueError):require_table('dbw_canopy_trial.gold.final_trips',role)
 def test_config_and_only_hgb_artifact(self):
  import yaml
  c=yaml.safe_load((ROOT/'databricks.yml').read_text());v=c['variables']
  self.assertEqual(v['event_hubs_topic']['default'],'evh-canopy-sandbox-5dt024')
  self.assertEqual(v['ingestion_continuous_pause_status']['default'],'PAUSED')
  workspace=c['targets']['sandbox']['workspace']
  self.assertEqual(workspace['root_path'],'/Workspace/bundles/.bundle/canopy/${bundle.name}/${bundle.target}')
  self.assertEqual(workspace['profile'],'CANOPY_TRIAL')
  self.assertIn('../../shared/*.yml',c['include'])
  self.assertNotIn('permissions',c)
  jobs=yaml.safe_load((ROOT/'resources/hgb.jobs.yml').read_text())['resources']['jobs']
  pipeline=yaml.safe_load((ROOT/'resources/sandbox_ingestion.pipeline.yml').read_text())['resources']['pipelines']['sandbox_ingestion']
  self.assertNotIn('permissions',pipeline)
  self.assertNotIn('run_as',pipeline)
  for job in jobs.values():
   self.assertEqual(job['permissions'],[{'group_name':'users','level':'CAN_MANAGE'}])
   self.assertEqual(job['run_as'],{'user_name':'${workspace.current_user.userName}'})
  self.assertEqual(jobs['sandbox_hgb_trip']['continuous']['pause_status'],'${var.production_trip_pause_status}')
  self.assertNotIn('schedule',jobs['sandbox_hgb_trip'])
  self.assertEqual(len(list(ROOT.rglob('*.joblib'))),1);self.assertFalse(list(ROOT.rglob('*.pth')))
if __name__=='__main__':unittest.main(verbosity=2)
