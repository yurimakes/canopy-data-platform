"""Original phone input/result processing; HGB replaces only model prediction."""
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT/'runtime/tools/local',ROOT/'runtime'):
    if str(path) not in sys.path:sys.path.append(str(path))
from model import LocalModel as OriginalModel, distance, stamp
from service.hgb_classifier import VERSION, features

def device_speed(point):
    value=point.get('raw_speed')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=200/3.6:
        return None
    return value*3.6


class PhoneModel(OriginalModel):
    def predict(self,points):
        return super().predict(points)

    def result(self,trip,points,transition_state=None):
        # HGB features derive speed from coordinates and timestamps. Device
        # speed is optional and must not reject otherwise valid GPS fixes.
        # Original coordinate accuracy, gap and impossible-speed checks remain.
        return super().result(trip,points,transition_state=transition_state)
