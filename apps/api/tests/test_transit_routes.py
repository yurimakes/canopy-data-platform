import io
import json
import unittest
from unittest.mock import patch
from services.trip_service import ApiError
from services import transit_routes as module
from trip_routes import dispatch


class TransitTests(unittest.TestCase):
    def setUp(self):
        module._cache.clear()
        module._last_call.clear()
        self.body = {"from": {"latitude": 37.55, "longitude": 126.97}, "to": {"latitude": 37.5, "longitude": 127.02}}

    def test_invalid_coordinates_never_call_provider(self):
        with patch.object(module.urllib.request, "urlopen") as call:
            self.body["from"]["latitude"] = 91
            with self.assertRaises(ApiError):
                module.transit_routes("user", self.body)
            call.assert_not_called()

    def test_proxy_preserves_route_and_hides_key(self):
        raw = {"metaData": {"plan": {"itineraries": [{"totalTime": 600, "totalDistance": 1000, "legs": []}]}}}
        with patch.dict(module.os.environ, {"TMAP_APP_KEY": "secret-test-value"}), patch.object(module.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(raw).encode())) as call:
            result = module.transit_routes("user", self.body)
            self.assertEqual(result, raw)
            self.assertNotIn("secret-test-value", json.dumps(result))
            self.assertEqual(module.transit_routes("user", self.body), raw)
            self.assertEqual(call.call_count, 1)

    def test_requires_existing_user_authentication(self):
        def reject(headers):
            raise ApiError(401, "unauthorized", "login required")
        with patch.object(module.urllib.request, "urlopen") as call:
            status, _ = dispatch("POST", "/api/routes/transit", {}, json.dumps(self.body).encode(), auth=reject)
            self.assertEqual(status, 401)
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
