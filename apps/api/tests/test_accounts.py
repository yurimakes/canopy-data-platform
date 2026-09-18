import copy
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from unittest.mock import patch

from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceExistsError, CosmosResourceNotFoundError
from services.accounts import Accounts, CampaignRegistry, account_id
from services.cosmos_service import SQLiteTripStore
from services.mock_trip_processor import MockTripProcessor
from services.runtime import authenticate
from services.trip_service import ApiError, TripService
from trip_routes import dispatch


class Container:
    def __init__(self):
        self.rows, self.lock = {}, Lock()

    def read_item(self, uid, partition_key):
        with self.lock:
            if uid not in self.rows:
                raise CosmosResourceNotFoundError(message="missing")
            assert uid == partition_key
            return copy.deepcopy(self.rows[uid])

    def create_item(self, doc):
        with self.lock:
            if doc['id'] in self.rows:
                raise CosmosResourceExistsError(message="duplicate")
            self.rows[doc['id']] = copy.deepcopy({**doc, '_etag': '1'})
            return copy.deepcopy(self.rows[doc['id']])

    def replace_item(self, uid, doc, etag, match_condition):
        with self.lock:
            if self.rows[uid]['_etag'] != etag:
                raise CosmosHttpResponseError(status_code=412, message="race")
            self.rows[uid] = copy.deepcopy({**doc, '_etag': str(int(etag) + 1)})
            return copy.deepcopy(self.rows[uid])


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.container = Container()
        self.now = 1_789_689_600
        self.api = Accounts(self.container, CampaignRegistry('campaign_test'), lambda: self.now)
        self.body = dict(email='user@example.com', password='my long unique password', nickname='사용자', campaign_code='TEST')

    def test_signup_password_storage_and_public_projection(self):
        result = self.api.signup(self.body)
        doc = self.api.authenticated(result['access_token'])
        self.assertEqual(doc['created_at'], doc['campaign_joined_at'])
        self.assertEqual(doc['campaign_id'], 'campaign_test')
        self.assertNotIn(self.body['password'], json.dumps(doc))
        self.assertNotIn(result['access_token'], json.dumps(doc))
        self.assertNotIn('credentials', result['profile'])
        self.assertNotIn('sessions', result['profile'])
        self.assertEqual(result['profile']['role'], 'user')

    def test_case_insensitive_duplicate_and_simultaneous_signup(self):
        def create(_):
            try:
                return self.api.signup(dict(self.body, email=' USER@EXAMPLE.COM '))['profile']['id']
            except ApiError as e:
                return e.status
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(create, range(2)))
        self.assertEqual(results.count(409), 1)
        self.assertEqual(len(self.container.rows), 1)

    def test_role_identity_and_campaign_cannot_be_injected(self):
        for key in ['role', 'id', 'user_id', 'campaign_id', 'campaign_joined_at']:
            with self.assertRaises(ApiError):
                self.api.signup({**self.body, key: 'developer'})
        for code in ['UNKNOWN', '', None]:
            with self.assertRaises(ApiError):
                self.api.signup(dict(self.body, campaign_code=code))
        self.assertFalse(self.container.rows)

    def test_server_developer_role_and_guard(self):
        dev = self.api.signup(dict(self.body, email='canopydev'), developer=True)
        regular = self.api.signup(self.body)
        for session, status in [(dev, 200), (regular, 403)]:
            actual, _ = dispatch('GET', '/api/auth/developer', {'Authorization': 'Bearer ' + session['access_token']}, b'', account_api=self.api)
            self.assertEqual(actual, status)
        self.assertEqual(self.api.login(dict(email='CANOPYDEV', password=self.body['password']))['profile']['role'], 'developer')

    def test_login_from_another_device_logout_only_one_session_and_expiry(self):
        first = self.api.signup(self.body)
        second = self.api.login({k: self.body[k] for k in ('email', 'password')})
        self.assertEqual(first['profile'], second['profile'])
        self.api.logout(first['access_token'])
        with self.assertRaises(ApiError):
            self.api.authenticated(first['access_token'])
        self.api.authenticated(second['access_token'])
        self.now = second['expires_at']
        with self.assertRaises(ApiError):
            self.api.authenticated(second['access_token'])

    def test_wrong_password_lock_and_unknown_user(self):
        self.api.signup(self.body)
        for _ in range(10):
            with self.assertRaises(ApiError) as e:
                self.api.login(dict(email=self.body['email'], password='wrong'))
            self.assertEqual(e.exception.status, 401)
        with self.assertRaises(ApiError) as e:
            self.api.login(dict(email=self.body['email'], password=self.body['password']))
        self.assertEqual(e.exception.status, 429)
        self.now += 901
        self.api.login({k: self.body[k] for k in ('email', 'password')})
        with self.assertRaises(ApiError) as e:
            self.api.login(dict(email='unknown@example.com', password='wrong'))
        self.assertEqual(e.exception.status, 401)

    def test_update_preserves_participation_and_blocks_role_change(self):
        signed = self.api.signup(self.body)
        changed = self.api.update(signed['access_token'], {'nickname': '변경', 'home': {'name': '집', 'latitude': 37., 'longitude': 127.}})
        self.assertEqual(changed['created_at'], signed['profile']['created_at'])
        for key in ('role', 'email', 'campaign_id', 'campaign_code', 'campaign_joined_at'):
            with self.assertRaises(ApiError):
                self.api.update(signed['access_token'], {key: 'other'})
        with self.assertRaises(ApiError):
            self.api.update(signed['access_token'], {'work': {'name': 'x', 'latitude': float('nan'), 'longitude': 0}})

    def test_future_campaign_registration_window_and_trip_owner(self):
        self.api.campaigns = CampaignRegistry('ignored', {'TEAM': {'campaign_id': 'team_A', 'accepting_signups': True}, 'CLOSED': {'campaign_id': 'team_B', 'accepting_signups': False}})
        signed = self.api.signup(dict(self.body, campaign_code='team'))
        with self.assertRaises(ApiError):
            self.api.signup(dict(self.body, email='b@example.com', campaign_code='CLOSED'))
        with tempfile.TemporaryDirectory() as folder:
            trips = TripService(SQLiteTripStore(folder + '/trips.db'), MockTripProcessor(), campaign_id='wrong_default')
            headers = {'Authorization': 'Bearer ' + signed['access_token']}
            auth = lambda h: self.api.authenticated(h['authorization'][7:])['user_id']
            status, trip = dispatch('POST', '/api/trips/start', headers, json.dumps({'request_id': 'one', 'device_id': 'phone'}).encode(), trip_service=trips, auth=auth, account_api=self.api)
            self.assertEqual(status, 201)
            self.assertEqual(trip['campaign_id'], 'team_A')
            self.assertEqual(trip['user_id'], signed['profile']['id'])
            status, _ = dispatch('POST', '/api/trips/start', headers, b'{"request_id":"two","device_id":"phone","campaign_id":"forged"}', trip_service=trips, auth=auth, account_api=self.api)
            self.assertEqual(status, 403)
            with self.assertRaises(ApiError):
                trips.get(trip['trip_id'], 'other-user')

    def test_authenticate_uses_server_session_and_disabled_account(self):
        signed = self.api.signup(self.body)
        with patch.dict(os.environ, {'CANOPY_ACCOUNT_AUTH_ENABLED': 'true'}), patch('services.runtime.accounts', return_value=self.api):
            self.assertEqual(authenticate({'authorization': 'Bearer ' + signed['access_token']}), account_id(self.body['email']))
            self.container.rows[signed['profile']['id']]['account_disabled'] = True
            with self.assertRaises(ApiError):
                authenticate({'authorization': 'Bearer ' + signed['access_token']})

    def test_closed_window_and_missing_timezone(self):
        registry = CampaignRegistry('', {'TEST': {'campaign_id': 'x', 'accepting_signups': True, 'signup_ends_at': '2020-01-01T00:00:00Z'}})
        with self.assertRaises(ApiError):
            registry.resolve('TEST', self.now)
        registry.entries['TEST']['signup_ends_at'] = '2030-01-01T00:00:00'
        with self.assertRaises(RuntimeError):
            registry.resolve('TEST', self.now)

    def test_auth_route_rejects_large_malformed_and_non_object_body(self):
        for body, status in [(b'x' * 16385, 413), (b'[1]', 400), (b'{', 400)]:
            actual, _ = dispatch('POST', '/api/auth/signup', {}, body, account_api=self.api)
            self.assertEqual(actual, status)


if __name__ == '__main__':
    unittest.main()
