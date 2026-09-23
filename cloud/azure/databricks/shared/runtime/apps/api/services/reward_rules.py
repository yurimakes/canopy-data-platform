"""추가 보상의 순수 계산. 저장소·웹 프레임워크 의존성 제외."""
from decimal import Decimal, ROUND_DOWN
from math import isfinite


def journey_points(expected_kg, actual_kg, policy):
    for value in (expected_kg,actual_kg):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<0:
            raise ValueError('invalid carbon amount')
    rate=Decimal(str(policy['grams_per_token']))
    if rate<=0 or not rate.is_finite():raise ValueError('invalid conversion rate')
    saved=max(Decimal(0),Decimal(str(expected_kg))-Decimal(str(actual_kg)))
    amount=(saved*1000/rate).quantize(Decimal(1),rounding=ROUND_DOWN)
    return float(saved),min(int(amount),int(policy['trip_cap']))


def ranking_points(rank, policy):
    return int(policy['rank_awards'].get(str(rank),0))
