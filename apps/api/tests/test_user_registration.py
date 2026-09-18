import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import MagicMock
from azure.cosmos.exceptions import CosmosResourceNotFoundError,CosmosResourceExistsError
from services.user_registration import UserRegistration
from services.trip_service import ApiError
from trip_routes import dispatch
from datetime import datetime,timezone

class RegistrationTests(unittest.TestCase):
 def setUp(self):
  self.c=MagicMock();self.now=datetime(2026,9,18,tzinfo=timezone.utc)
  self.api=UserRegistration(self.c,'campaign_test',lambda:self.now)
  self.body={'campaign_code':'TEST','nickname':'테스트'}
 def document(self):
  return dict(id='u',user_id='u',campaign_id='campaign_test',created_at=self.now.isoformat(),campaign_joined_at=self.now.isoformat())
 def test_initial_registration_and_authenticated_owner(self):
  self.c.read_item.side_effect=CosmosResourceNotFoundError(message='missing')
  self.c.create_item.side_effect=lambda d:d
  status,result=dispatch('POST','/api/users/register',{},json.dumps(self.body).encode(),auth=lambda h:'u',registration_api=self.api)
  self.assertEqual(status,201);self.assertEqual(result['user_id'],'u')
  self.assertEqual(result['created_at'],result['campaign_joined_at'])
  self.assertEqual(result['created_at'],self.now.isoformat())
 def test_retry_and_concurrent_registration_preserve_dates(self):
  self.c.read_item.return_value=self.document()
  result,created=self.api.register('u',self.body)
  self.assertFalse(created);self.c.create_item.assert_not_called()
  self.c.read_item.side_effect=[CosmosResourceNotFoundError(message='missing'),self.document()]
  self.c.create_item.side_effect=CosmosResourceExistsError(message='race')
  self.assertEqual(self.api.register('u',self.body),(result,False))
 def test_no_campaign_reassignment_or_client_dates(self):
  for field in ['user_id','created_at','campaign_joined_at','password']:
   with self.assertRaises(ApiError):self.api.register('u',dict(self.body,**{field:'bad'}))
  self.c.read_item.return_value=dict(self.document(),campaign_id='other')
  with self.assertRaises(ApiError) as e:self.api.register('u',self.body)
  self.assertEqual(e.exception.status,409)
 def test_authentication_failure_does_not_write(self):
  def denied(h):raise ApiError(401,'unauthorized','login required')
  status,_=dispatch('POST','/api/users/register',{},b'{}',auth=denied,registration_api=self.api)
  self.assertEqual(status,401);self.c.create_item.assert_not_called()

if __name__=='__main__':unittest.main()
