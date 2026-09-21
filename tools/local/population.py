"""기존 KTDB 모델과 행정동 참조자료를 사용하는 오프라인 어댑터."""
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import sys
import math
import os

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = Path(os.getenv('CANOPY_KTDB_REFERENCE_ROOT',str(ROOT / '.local-data/reference-model')))
MODEL = Path(os.getenv('CANOPY_KTDB_MODEL_PATH',str(ROOT / '.local-data/models/ktdb_population_baseline.pkl')))
SHA256 = '790a9177f5dff5bcada6330fac7d65a2b2e2da3294e2e70351c36a78e08f523b'


@lru_cache
def model():
    from catboost import CatBoostClassifier
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != SHA256:
        raise ValueError('KTDB 모델 버전 확인 필요')
    result = CatBoostClassifier()
    result.load_model(str(MODEL))
    return result


def estimate(route, direction='outbound', at=None):
    from services.domain_context import backend
    provider=backend.get()
    if provider is not None:return provider.estimate(route,direction,at)
    if direction not in ('outbound', 'return'):
        raise ValueError('출퇴근 방향 확인 필요')
    if str(REFERENCE) not in sys.path:
        sys.path.insert(0, str(REFERENCE))
    from src.integration.ktdb_context import build_expected_features
    from src.integration.gps_contract import GpsEvent
    from src.ktdb.model_data import prepare_prediction_features
    from services.trip_carbon import carbon_for
    import pandas as pd
    timestamp = at or datetime.now(timezone.utc)
    events = [GpsEvent('local-route-v1', 'preview', 'local', i+1, timestamp,
              p['latitude'], p['longitude'], None, None, None, None, None)
              for i,p in enumerate((route['from'], route['to']))]
    context = build_expected_features(events, purpose='출근' if direction=='outbound' else '귀가',
                                     commute_direction='to_work' if direction=='outbound' else 'work_to_home')
    frame,_,_ = prepare_prediction_features(pd.DataFrame([context.features]))
    probabilities = dict(zip(map(str, model().classes_), map(float, model().predict_proba(frame)[0])))
    if not all(math.isfinite(p) and 0<=p<=1 for p in probabilities.values()):
        raise ValueError('KTDB 확률 결과 오류')
    meters = float(route['distance_m'])
    # Final Trip과 동일한 팀 배출계수로 확률 가중 기대 탄소량 산정
    parts = [dict(segment_id=mode, mode=mode, distance_m=meters*prob) for mode,prob in probabilities.items()]
    carbon = carbon_for(parts, 'mode')
    return {'expected_kg':carbon.emission_kgco2e, 'probabilities':probabilities,
            'features':context.features, 'provenance':context.provenance,
            'factor_version':carbon.factor_version, 'carbon_policy_version':carbon.policy_version,
            'model_version':'ktdb-population-'+SHA256[:12],
            'source':'KTDB 모델 · 인근 행정동 중심점 / 출발·도착 직선거리 기준'}


@lru_cache
def places():
    import pandas as pd
    from pyproj import Transformer
    rows=pd.read_csv(REFERENCE/'data/reference/admin_dong_centroids_2021.csv',dtype={'adm_cd':str})
    transform=Transformer.from_crs('EPSG:5179','EPSG:4326',always_xy=True)
    result=[]
    for r in rows.to_dict('records'):
        lon,lat=transform.transform(r['x'],r['y'])
        result.append({'id':r['adm_cd'],'name':r['adm_nm'],'address':'행정동 중심점 · 오프라인 참조 위치',
                       'latitude':lat,'longitude':lon})
    return result


def search(query):
    terms=query.strip().split()
    return [p for p in places() if terms and all(t in p['name'] for t in terms)][:20]
