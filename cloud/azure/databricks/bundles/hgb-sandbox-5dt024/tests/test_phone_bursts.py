import ast,sys,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.phone_model import PhoneModel

def body(path,cls):
 t=ast.parse(path.read_text(encoding='utf-8'))
 c=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name==cls)
 return ast.dump(next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='result'))

class OriginalFlow(unittest.TestCase):
 def test_result_methods_are_identical_to_production(self):
  for file,cls in [('service/phone_model.py','PhoneModel'),('runtime/tools/local/model.py','LocalModel')]:
   self.assertEqual(body(ROOT/file,cls),body(ROOT.parent/'production-trip'/file,cls))
  for file in ['service/live_predictions.py','runtime/cloud/azure/pipelines/gps_streaming/quality.py','runtime/tools/local/transit_fusion.py']:
   self.assertEqual((ROOT/file).read_bytes(),(ROOT.parent/'production-trip'/file).read_bytes())
 def test_short_segments_and_final_tail_are_classified_without_new_filters(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc)
  points=[dict(event_time=(t+timedelta(seconds=i)).isoformat(),lat=37.55+i*.000008,lon=126.99,accuracy=5.,altitude_m=10.) for i in range(46)]
  model=PhoneModel();seen=[]
  def predict(p):
   seen.append(p);return {'walk':1.,'bike':0.,'car':0.,'bus':0.,'rail':0.},{}
  with patch.object(model,'predict_window',side_effect=predict):rows=model.predict(points)
  self.assertEqual([(r['begin'],r['end']) for r in rows],[(0,20),(20,40),(40,45)])
  self.assertEqual(seen[-1],points)
 def test_nearby_timestamps_are_not_coalesced(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc)
  p=[dict(event_time=(t+timedelta(milliseconds=i*30)).isoformat(),lat=37.55,lon=127.,accuracy=5.) for i in range(3)]
  model=PhoneModel()
  with patch.object(model,'predict_window',return_value=({'walk':1.},{})) as predict:
   model.predict(p)
   self.assertEqual(predict.call_args.args[0],p)
if __name__=='__main__':unittest.main()
