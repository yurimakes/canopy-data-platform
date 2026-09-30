"""Shared calculation-only quality gate. Raw observations are never modified."""
import math

QUALITY_VERSION='gps-quality-v1'
MAX_ACCURACY_M=100.0
MAX_GAP_SECONDS=120.0
MAX_SPEED_KMH=200.0

def transition_issue(previous_accuracy,accuracy,seconds,speed_kmh):
    if seconds<=0 or not math.isfinite(seconds):return 'non_positive_dt'
    if seconds>MAX_GAP_SECONDS:return 'collection_gap'
    for value in (previous_accuracy,accuracy):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=MAX_ACCURACY_M:
            return 'poor_accuracy'
    if not math.isfinite(speed_kmh) or speed_kmh>MAX_SPEED_KMH:return 'speed_above_200_kmh'
    return None
