import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from services.cosmos_service import SQLiteTripStore
from services.mock_trip_processor import ConfirmationFixtureProcessor
from services.trip_service import ApiError, TripService
from services.trip_feedback import SQLiteFeedbackStore, TripFeedbackService


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.now = datetime(2026, 9, 15, tzinfo=timezone.utc)
        self.trips = TripService(SQLiteTripStore(str(root/'trip.sqlite')), ConfirmationFixtureProcessor(),
                                 lambda: self.now, grace_seconds=0)
        self.feedback = SQLiteFeedbackStore(str(root/'feedback.sqlite'))
        self.api = TripFeedbackService(self.trips, self.feedback)
        trip, _ = self.trips.start('alice', {'request_id':'start','device_id':'phone'})
        self.id = trip['trip_id']
        self.now += timedelta(seconds=30)
        self.trips.stop(self.id, 'alice', {})
        self.trips.process_pending()
        self.original = self.trips.get(self.id, 'alice')

    def submit(self, issue=True, text=None, **extra):
        return self.api.submit(self.id, 'alice', {'request_id':'feedback-1','has_issue':issue,'feedback_text':text,**extra})

    def assert_result_unchanged(self):
        actual = self.trips.get(self.id, 'alice')
        for key, value in self.original.items():
            if key != '_etag': self.assertEqual(actual[key], value, key)

    def test_no_issue_writes_only_trip_and_duplicate_does_not_write(self):
        result = self.submit(False)
        self.assertFalse(result['review_required'])
        self.assertEqual(result['feedback_status'], 'no_issue')
        self.assertEqual(self.feedback.pending(), [])
        with self.feedback.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM trips').fetchone()[0], 0)
        self.assertEqual(self.submit(False)['_etag'], result['_etag'])
        self.assert_result_unchanged()

    def test_http_feedback_and_legacy_defaults(self):
        from trip_routes import dispatch
        from services.trip_service import public
        def request(body, user='alice', path=None):
            return dispatch('POST', path or f'/api/trips/{self.id}/feedback', {}, json.dumps(body).encode(),
                            self.trips, auth=lambda _: user, feedback_api=self.api)
        old = public(self.original)
        self.assertFalse(old['review_required'])
        self.assertIsNone(old['feedback_status'])
        self.assertIsNone(old['has_issue'])
        self.assertIn(request({'request_id':'1','has_issue':True}, user='bob')[0], (403,404))
        self.assertEqual(request({'request_id':'1','has_issue':True}, path='/api/trips/invalid%20id/feedback')[0],404)
        status, result = request({'request_id':'1','has_issue':True,'feedback_text':'test'})
        self.assertEqual(status,200)
        self.assertTrue(result['review_required'])
        self.assertNotIn('feedback_submission', result)
        self.assertNotIn('feedback_text', result)

    def test_unicode_limit_and_invalid_surrogate(self):
        from services.trip_feedback import validate_feedback
        self.assertEqual(validate_feedback({'request_id':'1','has_issue':True,'feedback_text':'😀'*500})[2], '😀'*500)
        for text in ('😀'*501, chr(0xD800)):
            with self.assertRaises(ApiError) as error:
                validate_feedback({'request_id':'1','has_issue':True,'feedback_text':text})
            self.assertEqual(error.exception.status,400)

    def test_result_has_carbon_before_any_feedback(self):
        self.assertEqual(self.original['confirmed_trip']['total_carbon_kg'], .778224)
        self.assertEqual(self.original['confirmed_trip']['bus_distance_m'], 6200)
        self.assertEqual(self.original['confirmed_trip']['mode_source'], 'model_prediction')
        self.assertEqual(self.original['confirmation_source'], 'system')
        self.assertTrue(all(s['confirmed_mode'] is None for s in self.original['segments']))
        with patch('services.trip_carbon.carbon_for', side_effect=AssertionError('must not recalculate')):
            self.submit(True, 'car')
        self.assert_result_unchanged()

    def test_issue_text_and_empty_are_accepted_without_modifying_result(self):
        text = '버스로 나왔는데 실제로는 자동차였습니다.'
        result = self.submit(True, text)
        document = self.feedback.read(result['feedback_id'], 'alice')
        self.assertEqual(document['feedback_text'], text)
        self.assertEqual(document['review_status'], 'pending')
        self.assertTrue(result['review_required'])
        self.assertNotIn('feedback_text', result)
        self.assertTrue(document['trip_flag_applied'])
        self.assert_result_unchanged()

    def test_optional_text_and_parallel_duplicate_requests(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.submit(True), range(6)))
        self.assertEqual(len({r['feedback_id'] for r in results}), 1)
        doc = self.feedback.read(results[0]['feedback_id'], 'alice')
        self.assertIsNone(doc['feedback_text'])
        with self.feedback.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM trips').fetchone()[0], 1)
        self.assert_result_unchanged()

    def test_invalid_payload_owner_and_conflicting_response(self):
        for changes in ({'has_issue':1}, {'feedback_text':123}, {'feedback_text':'가'*501}, {'mode':'car'}):
            with self.assertRaises(ApiError): self.submit(**({'issue':True,'text':None}), **changes)
        with self.assertRaises(ApiError): self.api.submit(self.id, 'bob', {'request_id':'1','has_issue':True})
        self.submit(False)
        with self.assertRaises(ApiError) as error: self.submit(True)
        self.assertEqual(error.exception.status, 409)
        self.assertFalse(self.trips.get(self.id, 'alice')['review_required'])

    def test_feedback_create_failure_is_pending_and_retryable(self):
        with patch.object(self.feedback, 'create', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError): self.submit(True, 'test')
        trip = self.trips.get(self.id, 'alice')
        self.assertEqual(trip['feedback_status'], 'pending')
        self.assertFalse(trip['review_required'])
        self.assertEqual(self.submit(True, 'test')['feedback_status'], 'submitted')
        self.assert_result_unchanged()

    def test_trip_flag_failure_recovers_from_feedback_without_phone(self):
        original_replace = self.trips.store.replace
        def fail_flag(item):
            if item.get('feedback_status') == 'submitted': raise RuntimeError('offline')
            return original_replace(item)
        with patch.object(self.trips.store, 'replace', side_effect=fail_flag):
            with self.assertRaises(RuntimeError): self.submit(True, 'repair')
        self.assertEqual(len(self.feedback.pending()), 1)
        self.assertEqual(self.api.recover_pending(), 1)
        self.assertEqual(self.feedback.pending(), [])
        self.assertTrue(self.trips.get(self.id, 'alice')['review_required'])
        self.assert_result_unchanged()
