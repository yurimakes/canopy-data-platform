import sys,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from service.phone_model import PhoneModel,coalesce_gps_bursts

class PhoneBursts(unittest.TestCase):
 def point(self,t,lat=37.55,accuracy=10):
  return dict(event_time=t.isoformat(),lat=lat,lon=126.99,accuracy=accuracy,altitude_m=10)
 def test_overlapping_burst_selects_original_more_accurate_fix(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc)
  a=self.point(t,accuracy=20);b=self.point(t+timedelta(milliseconds=30),lat=37.55003,accuracy=10)
  self.assertEqual(coalesce_gps_bursts([a,b]),[b])
  self.assertEqual(a['accuracy'],20)
 def test_long_chain_is_not_collapsed_and_real_jumps_remain(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc)
  p=[self.point(t+timedelta(milliseconds=i*40)) for i in range(7)]
  self.assertEqual(len(coalesce_gps_bursts(p)),3)
  a=self.point(t);b=self.point(t+timedelta(milliseconds=30),lat=38.)
  self.assertEqual(coalesce_gps_bursts([a,b]),[a,b])
  b={**b,'lat':a['lat'],'accuracy':None}
  self.assertEqual(coalesce_gps_bursts([a,b]),[a,b])
 def test_phone_bursts_no_longer_destroy_complete_window(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);p=[]
  for i in range(131):
   p.append(self.point(t+timedelta(seconds=i),37.55+i*.000008,20))
   if i in (40,60,80):p.append(self.point(t+timedelta(seconds=i,milliseconds=30),37.55+i*.000008+.00003,10))
  trip=dict(trip_id='test',started_at=t.isoformat(),ended_at=(t+timedelta(seconds=130)).isoformat())
  r=PhoneModel().result(trip,p)
  self.assertTrue(r['segments'])
  self.assertFalse(any(x['reason']=='speed_above_200_kmh' for x in r['data_quality']['excluded_intervals']))
  # A spatially distinct callback still splits the run; do not hide a real jump.
  p[41]['lat']=38.
  r=PhoneModel().result(trip,p)
  self.assertTrue(any(x['reason']=='speed_above_200_kmh' for x in r['data_quality']['excluded_intervals']))
if __name__=='__main__':unittest.main()
