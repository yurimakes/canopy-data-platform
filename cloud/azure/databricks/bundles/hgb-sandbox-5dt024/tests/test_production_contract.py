import sys, unittest, tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'runtime/apps/api'),str(ROOT), str(ROOT/'runtime/cloud/azure/pipelines/databricks'),str(ROOT/'runtime/tools/local'),str(ROOT/'runtime/apps/api')]
from service.phone_model import PhoneModel
from infer_trip_batch import infer
from finalize_trip_pipeline import build_final_trip,publish_cosmos
from services.cosmos_service import SQLiteTripStore

class ProductionContract(unittest.TestCase):
 def test_hgb_through_original_finalization_and_cosmos_contract(self):
  import os
  os.environ['CANOPY_KTDB_REFERENCE_ROOT']=str(ROOT)
  os.environ['CANOPY_TRANSIT_REFERENCE_DIR']=str(ROOT/'assets/transit')
  start=datetime(2026,9,24,tzinfo=timezone.utc)
  points=[{'user_id':'test-user','trip_id':'test-trip','sequence':i+1,'event_time':(start+timedelta(seconds=i)).isoformat(),'lat':37.55+i*.000008,'lon':126.99,'accuracy':5.,'raw_speed':1.} for i in range(241)]
  trip={'id':'test-trip','type':'trip','trip_id':'test-trip','user_id':'test-user','campaign_id':'test','started_at':points[0]['event_time'],'ended_at':points[-1]['event_time'],'expected_last_sequence':241,'processing_generation':1,'status':'processing','result_owner':'databricks'}
  result,verified=infer(trip,points,model=PhoneModel())
  context={k:trip[k] for k in ('trip_id','user_id','campaign_id','started_at','ended_at','processing_generation')}
  document=build_final_trip({'trip':context,'result':result,'completed_at':(start+timedelta(minutes=5)).isoformat()},lifecycle=trip)
  self.assertEqual(document['status'],'ready');self.assertTrue(document['model_version'].startswith('hgb-'))
  with tempfile.TemporaryDirectory() as tmp:
   store=SQLiteTripStore(tmp+'/trip.sqlite');store.create(trip)
   self.assertEqual(publish_cosmos(store,document),'published')
   self.assertEqual(publish_cosmos(store,document),'already_published')
   saved=store.read('test-trip','test-user')
   self.assertEqual(saved['carbon']['kg_co2e'],0)
   self.assertEqual(saved['segments'][0]['model_prediction'],'walk')
   self.assertEqual(saved['confirmed_trip']['confirmation_source'],'system')
 def test_canonical_storage_code_is_unchanged(self):
  original=ROOT.parent/'production-trip'
  for path in ['runtime/cloud/azure/pipelines/databricks/finalize_trip_pipeline.py','runtime/cloud/azure/pipelines/databricks/infer_trip_batch.py','runtime/cloud/azure/pipelines/databricks/trip_delta_store.py','service/gps_reader.py']:
   self.assertEqual((ROOT/path).read_bytes(),(original/path).read_bytes(),path)
if __name__=='__main__':unittest.main()
