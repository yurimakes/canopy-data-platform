import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "cloud/azure/pipelines/databricks"
sys.path.insert(0, str(RUNTIME))
from baseline_eligibility import (load_eligibility_policy, evaluate_personal_eligibility,
                                  evaluate_global_eligibility, observation_context)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_eligibility_policy()

    def test_personal_A_to_E(self):
        for case, days, trips, distance, carbon, expected in [
            ("A", 6, 6, 1000, 1, "collecting"),
            ("B", 7, 5, 1000, 1, "collecting"),
            ("C", 7, 6, 1000, 1, "ready"),
            ("D", 7, 6, 0, 1, "collecting"),
            ("E", 7, 6, 1000, None, "collecting"),
        ]:
            with self.subTest(case=case):
                result = evaluate_personal_eligibility(days, trips, distance, carbon, self.policy)
                self.assertEqual(result["status"], expected)

    def test_global_F_G_H_counts_are_eligible_not_registered(self):
        for case, count, status in [("F", 5, "collecting"), ("G", 6, "ready"), ("H", 4, "collecting")]:
            with self.subTest(case=case):
                self.assertEqual(evaluate_global_eligibility(count, self.policy)["status"], status)

    def test_thresholds_come_from_yaml_not_gate_constants(self):
        p = copy.deepcopy(self.policy)
        p["personal"]["minimum_observation_days"] = 9
        p["personal"]["minimum_confirmed_commute_trips"] = 8
        p["global"]["minimum_eligible_participants"] = 3
        self.assertEqual(evaluate_personal_eligibility(7, 6, 1, 0, p)["status"], "collecting")
        self.assertEqual(evaluate_personal_eligibility(9, 8, 1, 0, p)["status"], "ready")
        self.assertEqual(evaluate_global_eligibility(3, p)["status"], "ready")

    def test_invalid_numbers_and_zero_emissions(self):
        for carbon in (None, float("nan"), float("inf"), -1, True, "1"):
            self.assertEqual(evaluate_personal_eligibility(7, 6, 1, carbon, self.policy)["status"], "collecting")
        self.assertEqual(evaluate_personal_eligibility(7, 6, 1, 0, self.policy)["status"], "ready")

    def test_membership_priority_elapsed_days_and_legacy_user_fallback(self):
        data = {"users": [{"user_id": "u", "created_at": "2026-01-01T00:00:00Z"}],
                "memberships": [{"user_id": "u", "campaign_id": "c", "joined_at": "2026-09-01T09:00:00+09:00"}]}
        self.assertEqual(observation_context("u", "c", "2026-09-08T00:00:00Z", data)[:2], (7, "membership.joined_at"))
        self.assertEqual(observation_context("u", "c", "2026-09-07T23:59:59Z", data)[0], 6)
        self.assertEqual(observation_context("u", "other", "2026-09-08T00:00:00Z", data)[1], "user.created_at")
        self.assertEqual(observation_context("missing", "c", "2026-09-08T00:00:00Z", data)[2], "joined_at_missing")
        data["memberships"][0]["joined_at"] = "invalid"
        self.assertEqual(observation_context("u", "c", "2026-09-08T00:00:00Z", data)[2], "invalid_joined_at")


if __name__ == "__main__":
    unittest.main()
