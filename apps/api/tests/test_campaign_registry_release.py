import json
import unittest
from unittest.mock import patch
from services.accounts import CampaignRegistry
from services.trip_service import ApiError

class CampaignReleaseTests(unittest.TestCase):
    def test_production_missing_registry_denies_test(self):
        with patch.dict('os.environ', {'TRIP_CAMPAIGN_ID':'existing','WEBSITE_HOSTNAME':'main'}, clear=True):
            with self.assertRaises(ApiError): CampaignRegistry.from_env().resolve('TEST',0)

    def test_only_msds_accepted(self):
        env={'TRIP_CAMPAIGN_ID':'existing','CANOPY_CAMPAIGNS_JSON':json.dumps({'MSDS':{'campaign_id':'existing','accepting_signups':True}})}
        with patch.dict('os.environ',env,clear=True):
            registry=CampaignRegistry.from_env()
            self.assertEqual(registry.resolve(' msds ',0),('MSDS','existing'))
            for code in ['TEST','CANOPYTEST','UNKNOWN','']:
                with self.subTest(code=code),self.assertRaises(ApiError):registry.resolve(code,0)

    def test_closed_campaign_denied(self):
        registry=CampaignRegistry('existing',{'MSDS':{'campaign_id':'existing','accepting_signups':False}})
        with self.assertRaises(ApiError):registry.resolve('MSDS',0)
