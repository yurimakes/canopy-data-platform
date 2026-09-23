import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone,timedelta
import unittest
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'service'),str(ROOT/'runtime/tools/local'),str(ROOT/'runtime')]
from phone_model import PhoneModel,device_speed


class Capture:
    def __call__(self,values,src_key_padding_mask):
        self.values=values;self.mask=src_key_padding_mask
        return torch.zeros((len(values),5))


class PhoneModelTests(unittest.TestCase):
    def model(self):
        m=PhoneModel.__new__(PhoneModel);m.torch=torch;m.model=Capture()
        m.scaler=SimpleNamespace(transform=lambda frame:frame.to_numpy())
        m.labels=SimpleNamespace(classes_=['bike','bus','car','train','walk'])
        return m
    def points(self,n):
        start=datetime(2026,9,21,tzinfo=timezone.utc)
        return [{'event_time':(start+timedelta(seconds=i)).isoformat(),'lat':37+i*.0002,'lon':127.,'raw_speed':1.5} for i in range(n)]
    def test_device_speed_not_coordinate_jitter(self):
        m=self.model();m.predict(self.points(4))
        self.assertTrue(torch.allclose(m.model.values[0,:3,0],torch.full((3,),5.4)))
    def test_padding_is_masked_and_not_repeated_measurements(self):
        m=self.model();m.predict(self.points(4))
        self.assertEqual(m.model.mask[0].sum().item(),197)
        self.assertTrue(torch.all(m.model.values[0,3:]==0))
    def test_full_window_has_no_padding(self):
        m=self.model();m.predict(self.points(201))
        self.assertEqual(m.model.mask[-1].sum().item(),0)
    def test_invalid_device_values_cannot_enter_features(self):
        for v in [None,-1,float('nan'),float('inf'),True,100]:
            self.assertIsNone(device_speed({'raw_speed':v}))
        self.assertEqual(device_speed({'raw_speed':0}),0)


if __name__=='__main__':unittest.main()
