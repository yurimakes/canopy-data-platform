import unittest
from services.trip_service import TripService
from trip_routes import dispatch


class Store:
    def read(self,trip_id,user_id):
        return {'id':'trip1','trip_id':'trip1','type':'trip','user_id':'owner',
                'status':'collecting','_etag':'private','live_prediction':{
                    'mode':'walk','sequence':12,'observed_at':'2026-09-21T11:00:00Z',
                    'updated_at':'2026-09-21T11:00:03Z','model_version':'test',
                    'provisional':True,'confidence':.9}}


class LivePredictionContract(unittest.TestCase):
    def test_owner_reads_live_result_through_existing_trip_route(self):
        status,body=dispatch('GET','/api/trips/trip1',{},b'',
            trip_service=TripService(Store(),None),auth=lambda headers:'owner')
        self.assertEqual(status,200)
        self.assertEqual(body['live_prediction']['mode'],'walk')
        self.assertEqual(body['status'],'collecting')
        self.assertNotIn('_etag',body)
    def test_other_user_cannot_read_live_result(self):
        status,body=dispatch('GET','/api/trips/trip1',{},b'',
            trip_service=TripService(Store(),None),auth=lambda headers:'other')
        self.assertEqual(status,403)
        self.assertNotIn('live_prediction',body)


if __name__=='__main__':unittest.main()
