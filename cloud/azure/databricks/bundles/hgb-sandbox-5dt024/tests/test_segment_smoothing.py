import sys, unittest, copy, subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'runtime/tools/local')]
from service.segment_smoothing import smooth_modes, TransitionState, stationary
from service.transit_fusion import preserve_bus_continuity

class SmoothingTests(unittest.TestCase):
 def rows(self,modes):
  start=datetime(2026,1,1,tzinfo=timezone.utc)
  return [dict(mode=m,run=0,start_time=(start+timedelta(seconds=i*10)).isoformat(),end_time=(start+timedelta(seconds=(i+1)*10)).isoformat(),confidence=.8,probabilities={x:(.8 if x==m else .05) for x in ('walk','bike','car','bus','rail')},stationary=False) for i,m in enumerate(modes)]
 def test_spike_removed_source_unchanged(self):
  rows=self.rows(['car','bus','car']);before=copy.deepcopy(rows)
  self.assertEqual([x['mode'] for x in smooth_modes(rows)],['car']*3)
  self.assertEqual(rows,before)
 def test_confirmation_backdates_candidate_not_window(self):
  rows=self.rows(['car','walk','walk','walk'])
  out=smooth_modes(rows)
  self.assertEqual([x['mode'] for x in out],['car','walk','walk','walk'])
  self.assertEqual([x['start_time'] for x in out],[x['start_time'] for x in rows])
 def test_two_strong_of_three_required(self):
  rows=self.rows(['car','walk','walk','walk'])
  rows[1]['probabilities']={'walk':.4,'car':.35}
  self.assertEqual(smooth_modes(rows)[-1]['mode'],'walk')
  rows[2]['probabilities']={'walk':.4,'car':.35}
  self.assertEqual([r['mode'] for r in smooth_modes(rows)],['car']*4)
 def test_candidate_reset_and_tail(self):
  rows=self.rows(['car','walk','walk','car','walk','walk'])
  self.assertEqual([x['mode'] for x in smooth_modes(rows)],['car']*6)
 def test_quality_gap_does_not_confirm(self):
  rows=self.rows(['walk','car','car','car'])
  rows[3]['run']=1
  self.assertEqual([x['mode'] for x in smooth_modes(rows)],['walk']*4)
 def test_stationary_hold_and_missing_speed(self):
  rows=self.rows(['car','bike','bike','bike'])
  for row in rows[1:]:row['stationary']=True
  self.assertEqual([x['mode'] for x in smooth_modes(rows)],['car']*4)
  self.assertFalse(stationary([{'raw_speed':None}]*10))
  self.assertTrue(stationary([{'raw_speed':.1}]*10))
 def test_stop_restart_and_transfer_for_every_mode(self):
  modes=['walk','bike','car','bus','rail']
  for old in modes:
   new=next(m for m in modes if m!=old)
   rows=self.rows([old,new,new,new,old,new,new,new])
   for row in rows[1:4]:row['stationary']=True
   out=smooth_modes(rows)
   self.assertEqual([r['mode'] for r in out[:5]],[old]*5)
   self.assertEqual([r['mode'] for r in out[5:]],[new]*3)
 def test_actual_rail_transition_preserved(self):
  self.assertEqual([r['mode'] for r in smooth_modes(self.rows(['bus','rail','rail','rail']))],['bus','rail','rail','rail'])
 def test_live_repeated_rows_do_not_confirm(self):
  state=TransitionState();rows=self.rows(['car','walk','walk','walk'])
  smooth_modes(rows[:2],state)
  for _ in range(5):smooth_modes(rows[:2],state)
  self.assertEqual(state.active,'car')
  smooth_modes(rows,state);self.assertEqual(state.active,'walk')
 def test_resident_worker_import_signature(self):
  code="import sys,inspect;sys.path[:0]=["+repr(str(ROOT/'service'))+","+repr(str(ROOT))+"];import resident_worker;from service.transit_fusion import fuse;assert 'previous_mode' in inspect.signature(fuse).parameters"
  subprocess.run([sys.executable,'-c',code],check=True)
 def test_bus_guard_preserves_model_rail(self):
  d={'final_mode':'rail','decision_confidence':.9}
  self.assertEqual(preserve_bus_continuity(d,{'bus':.92,'rail':.08},'bus')['final_mode'],'bus')
  self.assertEqual(preserve_bus_continuity(d,{'bus':.1,'rail':.9},'bus'),d)
if __name__=='__main__':unittest.main()
