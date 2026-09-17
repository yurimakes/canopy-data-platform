"""TMAP 대중교통 경로 중계. 앱에 공급자 키 전달 제외."""
import copy
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from services.trip_service import ApiError

_lock = threading.Lock()
_cache = OrderedDict()
_last_call = OrderedDict()


def coordinates(body):
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_route", "출발지와 도착지가 필요합니다.")
    values = []
    for label in ("from", "to"):
        place = body.get(label)
        if not isinstance(place, dict):
            raise ApiError(400, "invalid_route", "출발지와 도착지 좌표가 필요합니다.")
        lat, lon = place.get("latitude"), place.get("longitude")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ApiError(400, "invalid_coordinate", "위치 좌표를 확인해주세요.")
        values.extend((lon, lat))
    if values[:2] == values[2:]:
        raise ApiError(400, "same_location", "출발지와 도착지를 다르게 선택해주세요.")
    return tuple(values)


def transit_routes(user_id, body):
    points = coordinates(body)
    key = os.getenv("TMAP_APP_KEY", "").strip()
    if not key:
        raise ApiError(503, "route_not_configured", "길찾기 서비스 연결 준비 중입니다.")
    now = time.monotonic()
    # 동일 위치의 짧은 재조회만 재사용. 캐시는 인스턴스별이며 전체 사용량 제한은 공급자 설정 기준
    with _lock:
        cached = _cache.get(points)
        if cached and now-cached[0] < 60:
            return copy.deepcopy(cached[1])
        if now-_last_call.get(user_id, -100) < 3:
            raise ApiError(429, "route_rate_limit", "잠시 후 다시 검색해주세요.")
        _last_call[user_id] = now
        _last_call.move_to_end(user_id)
        while len(_last_call) > 1024:
            _last_call.popitem(last=False)
    payload = dict(zip(("startX", "startY", "endX", "endY"), map(str, points)))
    payload.update(count=3, lang=0, format="json")
    req = urllib.request.Request("https://apis.openapi.sk.com/transit/routes", data=json.dumps(payload).encode(),
                                 headers={"appKey": key, "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ApiError(502, "route_response_too_large", "경로 응답 크기를 초과했습니다.")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise ApiError(429 if exc.code == 429 else 502, "route_provider_error", "길찾기 제공사의 응답을 확인할 수 없습니다.") from None
    except (OSError, ValueError):
        raise ApiError(502, "route_unavailable", "길찾기에 실패했습니다. 잠시 후 다시 시도해주세요.") from None
    if not isinstance(data, dict) or not isinstance(data.get("metaData", {}).get("plan", {}).get("itineraries"), list):
        raise ApiError(502, "route_invalid_response", "조회 가능한 대중교통 경로를 확인하지 못했습니다.")
    # 원본 응답에서 경로 정보만 반환. 키와 요청 헤더, 개인 프로필 제외
    result = {"metaData": {"plan": {"itineraries": data["metaData"]["plan"]["itineraries"]}}}
    with _lock:
        _cache[points] = (now, result)
        _cache.move_to_end(points)
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return copy.deepcopy(result)
