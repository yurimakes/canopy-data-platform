import sys
from pathlib import Path
from copy import deepcopy
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'service'),str(ROOT/'runtime/apps/api')]
from live_predictions import publish_live
from services.cosmos_service import Conflict


class Store:
    def __init__(self,status='collecting'):
        self.doc={'trip_id':'t','user_id':'u','status':status,'result_owner':'databricks','_etag':'1'}
        self.conflict=False
    def read(self,*args):return deepcopy(self.doc)
    def replace(self,doc):
        if self.conflict:raise Conflict()
        self.doc=doc


class LivePredictionTests(unittest.TestCase):
    def test_live_does_not_settle_or_reward(self):
        s=Store();before=deepcopy(s.doc)
        self.assertTrue(publish_live(s,before,{'sequence':3,'mode':'walk','provisional':True}))
        self.assertEqual({k:v for k,v in s.doc.items() if k!='live_prediction'},before)
    def test_collecting_trip_has_no_final_result_owner_yet(self):
        s=Store();s.doc.pop('result_owner')
        self.assertTrue(publish_live(s,s.doc,{'sequence':3,'mode':'walk'}))
        self.assertNotIn('result_owner',s.doc)
    def test_stopped_trip_is_never_overwritten(self):
        for status in ('processing','ready','failed'):
            s=Store(status)
            self.assertFalse(publish_live(s,s.doc,{'sequence':3}))
    def test_stop_race_and_out_of_order_updates(self):
        s=Store();s.conflict=True
        self.assertFalse(publish_live(s,s.doc,{'sequence':3}))
        s.conflict=False;s.doc['live_prediction']={'sequence':4}
        self.assertFalse(publish_live(s,s.doc,{'sequence':3}))


if __name__=='__main__':unittest.main()
