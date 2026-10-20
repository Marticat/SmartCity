"""Bounded HTTP adapters; no user position stored in logs or disk."""
import os
import time
from datetime import datetime, timezone
import httpx
from .config import USER_AGENT
from .schemas.models import Weather


class WeatherService:
    def __init__(self):
        self.cache = {}

    async def get(self, origin, visit_datetime=None):
        if os.getenv("WEATHER_ENABLED", "true").lower() == "false":
            return Weather()
        target = (visit_datetime or datetime.now(timezone.utc)).astimezone(timezone.utc)
        key = (round(origin.latitude, 2), round(origin.longitude, 2), target.strftime("%Y-%m-%dT%H"))
        cached = self.cache.get(key)
        if cached and time.monotonic()-cached[0] < 600:
            return cached[1]
        try:
            async with httpx.AsyncClient(timeout=5, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": key[0], "longitude": key[1], "hourly": "temperature_2m,wind_speed_10m",
                    "timezone": "UTC", "forecast_days": 16})
                response.raise_for_status()
                hourly = response.json()["hourly"]
                times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly["time"]]
                i = min(range(len(times)), key=lambda j: abs((times[j]-target).total_seconds()))
                if abs((times[i]-target).total_seconds()) > 3600:
                    return Weather()
                result = Weather(status="available", temperature_c=hourly["temperature_2m"][i],
                                 wind_kmh=hourly["wind_speed_10m"][i], observed_at=times[i].isoformat(),
                                 source_url="https://open-meteo.com/")
                if len(self.cache) > 128:
                    self.cache.clear()
                self.cache[key] = (time.monotonic(), result)
                return result
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            result = Weather()
            # A short outage cache avoids repeated requests while a provider is down.
            self.cache[key] = (time.monotonic() - 540, result)
            return result


class RoutingService:
    async def route(self, origin, poi, return_to_start=False):
        key = os.getenv("ORS_API_KEY")
        # Polygon centres are not verified entrances; no misleading routing to them.
        if not key or poi.coordinate_kind != "node":
            return None
        coordinates = [[origin.longitude, origin.latitude], [poi.longitude, poi.latitude]]
        if return_to_start:
            coordinates.append(coordinates[0])
        try:
            async with httpx.AsyncClient(timeout=8, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.post("https://api.openrouteservice.org/v2/directions/foot-walking/geojson",
                                             headers={"Authorization": key}, json={"coordinates": coordinates})
                response.raise_for_status()
                body = response.json()
                feature = body["features"][0]
                summary = feature["properties"]["summary"]
                segments = feature["properties"].get("segments", [])
                if not segments or summary["duration"] <= 0:
                    return None
                return {"distance_m": float(segments[0]["distance"]), "total_distance_m": float(summary["distance"]), "minutes": float(summary["duration"])/60,
                        "outbound_minutes": float(segments[0]["duration"])/60, "geometry": feature["geometry"]}
        except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
            return None
