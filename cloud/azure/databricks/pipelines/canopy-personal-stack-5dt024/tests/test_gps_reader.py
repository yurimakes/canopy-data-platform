import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'service'))
from gps_reader import merge_history


class HistoryFallbackTests(unittest.TestCase):
    def test_completes_history_without_duplicating_shared_events(self):
        a={'sequence':1,'raw_speed':1.};b={'sequence':2,'raw_speed':2.}
        self.assertEqual(sorted(merge_history([b],[a,b]),key=lambda p:p['sequence']),[a,b])
    def test_conflicting_measurements_fail_instead_of_selecting_one(self):
        with self.assertRaises(ValueError):
            merge_history([{'sequence':1,'raw_speed':1.}],[{'sequence':1,'raw_speed':2.}])
    def test_old_trip_before_fast_consumer_is_not_lost(self):
        self.assertEqual(merge_history([],[{'sequence':1}]),[{'sequence':1}])


if __name__=='__main__':unittest.main()
