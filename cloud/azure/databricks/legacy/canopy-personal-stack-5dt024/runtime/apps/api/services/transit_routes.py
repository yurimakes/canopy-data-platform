"""TMAP 대중교통 경로 중계. 앱에 공급자 키 전달 제외."""
import copy
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
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
    status = str(data.get("result", {}).get("status", "")) if isinstance(data, dict) else ""
    if status == "11":
        return walking_route(points, key)
    if status in ("12", "13", "14"):
        raise ApiError(422, "route_not_found", "선택한 위치 사이에 대중교통 경로가 없습니다. 주변 정류장이나 다른 목적지로 검색해주세요.")
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


def search_places(user_id, body):
    """장소명 검색 결과를 이름, 주소, 지도 좌표로 정리. 공급자 키는 서버에서만 사용."""
    query = body.get("query", "")
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 100:
        raise ApiError(400, "invalid_place_query", "장소 이름이나 주소를 2~100자로 입력해주세요.")
    key = (os.getenv("TMAP_POI_APP_KEY") or os.getenv("TMAP_APP_KEY", "")).strip()
    if not key:
        raise ApiError(503, "place_not_configured", "장소 검색 서비스 연결 준비 중입니다. 현재 위치는 사용할 수 있어요.")
    query = query.strip()
    now = time.monotonic()
    cache_key = ("places", query)
    with _lock:
        cached = _cache.get(cache_key)
        if cached and now-cached[0] < 60:
            return copy.deepcopy(cached[1])
        caller = ("places", user_id)
        if now-_last_call.get(caller, -100) < 1:
            raise ApiError(429, "place_rate_limit", "잠시 후 다시 검색해주세요.")
        _last_call[caller] = now
        while len(_last_call) > 1024:
            _last_call.popitem(last=False)
    params = urllib.parse.urlencode({"version": "1", "searchKeyword": query, "searchType": "all",
        "count": "20", "page": "1", "resCoordType": "WGS84GEO", "reqCoordType": "WGS84GEO"})
    req = urllib.request.Request("https://apis.openapi.sk.com/tmap/pois?"+params,
                                 headers={"appKey": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ApiError(502, "place_response_too_large", "검색 결과를 불러오지 못했습니다.")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ApiError(503, "place_not_configured", "장소 검색 서비스 연결 준비 중입니다. 현재 위치는 사용할 수 있어요.") from None
        raise ApiError(429 if exc.code == 429 else 502, "place_provider_error", "장소 검색을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.") from None
    except (OSError, ValueError):
        raise ApiError(502, "place_unavailable", "장소 검색 응답이 늦어지고 있습니다. 다시 시도해주세요.") from None
    if not isinstance(data, dict) or not isinstance(data.get("searchPoiInfo"), dict):
        raise ApiError(502, "place_invalid_response", "장소 검색 결과를 확인하지 못했습니다.")
    items = data["searchPoiInfo"].get("pois", {}).get("poi", [])
    places = []
    for item in items:
        try:
            lat, lon = float(item["noorLat"]), float(item["noorLon"])
            name = str(item.get("name", "")).strip()
            if not name or not math.isfinite(lat) or not math.isfinite(lon) or not (-90<=lat<=90 and -180<=lon<=180):
                continue
            roads = item.get("newAddressList", {}).get("newAddress", [])
            road = next((x["fullAddressRoad"] for x in roads if x.get("fullAddressRoad")), "")
            address = road or " ".join(str(item.get(k) or "") for k in ("upperAddrName", "middleAddrName", "lowerAddrName", "detailAddrName")).strip()
            places.append({"id": str(item.get("id") or len(places)), "name": name, "address": address,
                           "latitude": lat, "longitude": lon})
        except (KeyError, TypeError, ValueError):
            continue
    result = {"places": places}
    with _lock:
        _cache[cache_key] = (now, result)
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return result


def walking_route(points, key):
    """대중교통 검색의 근거리 응답을 실제 TMAP 도보 경로로 연결."""
    payload = dict(zip(("startX", "startY", "endX", "endY"), points))
    payload.update(startName="start", endName="end", reqCoordType="WGS84GEO", resCoordType="WGS84GEO")
    req = urllib.request.Request("https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1",
        data=json.dumps(payload).encode(), headers={"appKey": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(4_000_001)
            if len(raw)>4_000_000:
                raise ValueError("response too large")
            data = json.loads(raw)
        features = data["features"]
        summary = next(f["properties"] for f in features if "totalDistance" in f.get("properties", {}))
        distance, duration = summary["totalDistance"], summary["totalTime"]
        if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in (distance,duration)):
            raise ValueError("invalid route totals")
        lines = [f["geometry"]["coordinates"] for f in features if f.get("geometry", {}).get("type")=="LineString"]
        steps = [{"linestring":" ".join(str(x)+","+str(y) for x,y in line)} for line in lines]
        return {"metaData":{"plan":{"itineraries":[{"totalTime":duration,"totalDistance":distance,
            "fare":{"regular":{"totalFare":0}},"legs":[{"mode":"WALK","route":"도보","sectionTime":duration,
                "distance":distance,"steps":steps}]}]}}}
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        raise ApiError(422, "walking_unavailable", "가까운 거리라 대중교통 경로가 없고, 도보 경로도 불러오지 못했습니다. 잠시 후 다시 검색해주세요.") from None
