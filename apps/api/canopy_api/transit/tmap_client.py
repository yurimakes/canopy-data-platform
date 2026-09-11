from __future__ import annotations

import httpx


TMAP_TRANSIT_URL = "https://apis.openapi.sk.com/transit/routes"


class TmapTransitClient:
    def __init__(self, app_key: str, timeout_s: float = 15.0):
        if not app_key:
            raise ValueError("TMAP app key is required")
        self.app_key = app_key
        self.timeout_s = timeout_s

    async def routes(
        self,
        *,
        start_lon: float,
        start_lat: float,
        end_lon: float,
        end_lat: float,
        count: int = 10,
        search_dttm: str | None = None,
    ) -> dict:
        body = {
            "startX": str(start_lon),
            "startY": str(start_lat),
            "endX": str(end_lon),
            "endY": str(end_lat),
            "count": max(1, min(int(count), 10)),
            "lang": 0,
            "format": "json",
        }
        if search_dttm:
            body["searchDttm"] = search_dttm

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "appKey": self.app_key,
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(TMAP_TRANSIT_URL, headers=headers, json=body)
            response.raise_for_status()
            return response.json()
