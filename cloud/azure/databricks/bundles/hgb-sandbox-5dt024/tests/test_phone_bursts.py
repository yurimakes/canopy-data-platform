import sys,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.phone_model import PhoneModel
from service.hgb_classifier import stamp
from src.aihub.runtime import latest_rolling_window
from types import SimpleNamespace

class TimeWindowContract(unittest.TestCase):
 def points(self,seconds,step=1):
  t=datetime(2026,1,1,tzinfo=timezone.utc)
  return [dict(event_time=(t+timedelta(seconds=i*step)).isoformat(),lat=37.55+i*step*.000008,lon=126.99,accuracy=5.,altitude_m=10.,raw_speed=None) for i in range(int(seconds/step)+1)]
 def test_windows_match_original_runtime_at_different_sampling_rates(self):
  for step in (0.25,1,3):
   p=self.points(250,step);model=PhoneModel();seen=[]
   def predict(points):
    seen.append(points);return {'walk':1.,'bike':0.,'car':0.,'bus':0.,'rail':0.},{}
   with patch.object(model,'predict_window',side_effect=predict):rows=model.predict(p)
   events=[SimpleNamespace(timestamp=stamp(x['event_time']),point=x) for x in p]
   for window in seen:
    self.assertLessEqual((stamp(window[-1]['event_time'])-stamp(window[0]['event_time'])).total_seconds(),120)
   expected=latest_rolling_window(events)
   self.assertIn([x.point for x in expected[1]],seen)
   self.assertEqual(rows[0]['begin'],0);self.assertEqual(rows[-1]['end'],len(p)-1)
   self.assertTrue(all(a['end']==b['begin'] for a,b in zip(rows,rows[1:])))
 def test_missing_device_speed_does_not_exclude_valid_coordinates(self):
  p=self.points(150)
  for x in p[40:]:x['raw_speed']=1.
  trip={'trip_id':'test','started_at':p[0]['event_time'],'ended_at':p[-1]['event_time']}
  r=PhoneModel().result(trip,p)
  self.assertEqual(r['data_quality']['status'],'complete')
  self.assertEqual(r['segments'][0]['start_time'],p[0]['event_time'])
 def test_actual_collection_gap_remains_excluded(self):
  p=self.points(150);p+=self.points(150)
  for x in p[151:]:x['event_time']=(stamp(x['event_time'])+timedelta(seconds=400)).isoformat()
  trip={'trip_id':'test','started_at':p[0]['event_time'],'ended_at':p[-1]['event_time']}
  r=PhoneModel().result(trip,p)
  self.assertIn('collection_gap',[x['reason'] for x in r['data_quality']['excluded_intervals']])
 def test_short_final_trip_is_not_padded_or_lost(self):
  p=self.points(45);model=PhoneModel()
  with patch.object(model,'predict_window',return_value=({'walk':1.},{})) as predict:
   rows=model.predict(p)
   self.assertEqual(predict.call_args.args[0],p)
   self.assertEqual([(r['begin'],r['end']) for r in rows],[(0,45)])
if __name__=='__main__':unittest.main()
