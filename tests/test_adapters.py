import asyncio
import httpx
from backend.app.schemas.models import Origin
from backend.app.services import RoutingService, WeatherService


def test_route_requires_walking_and_lon_lat_order(monkeypatch, poi_factory):
    observed = {}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            observed.update(url=url, body=kwargs["json"])
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "features":[{"properties":{"summary":{"distance":2000,"duration":1800},"segments":[{"duration":900,"distance":1000},{"duration":900,"distance":1000}]},
                             "geometry":{"type":"LineString","coordinates":[[71.41,51.09],[71.42,51.10],[71.41,51.09]]}}]})
    monkeypatch.setenv("ORS_API_KEY", "TEST_ONLY_NOT_A_KEY")
    monkeypatch.setattr("backend.app.services.httpx.AsyncClient", Client)
    result = asyncio.run(RoutingService().route(Origin(latitude=51.09, longitude=71.41),
                                                poi_factory(latitude=51.10, longitude=71.42), True))
    assert "/foot-walking/" in observed["url"]
    assert observed["body"]["coordinates"] == [[71.41, 51.09],[71.42,51.10],[71.41,51.09]]
    assert result["minutes"] == 30
    assert result["outbound_minutes"] == 15
    assert result["distance_m"] == 1000
    assert result["total_distance_m"] == 2000


def test_polygon_center_never_used_as_verified_entrance(monkeypatch, poi_factory):
    monkeypatch.setenv("ORS_API_KEY", "TEST_ONLY_NOT_A_KEY")
    result = asyncio.run(RoutingService().route(Origin(latitude=51.09, longitude=71.41),
                                                poi_factory(coordinate_kind="polygon_center")))
    assert result is None


def test_route_provider_failure_does_not_invent_path(monkeypatch, poi_factory):
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): raise httpx.ConnectError("TEST offline")
    monkeypatch.setenv("ORS_API_KEY", "TEST_ONLY_NOT_A_KEY")
    monkeypatch.setattr("backend.app.services.httpx.AsyncClient", Client)
    assert asyncio.run(RoutingService().route(Origin(latitude=51.09, longitude=71.41), poi_factory())) is None


def test_weather_failure_is_unknown_not_fabricated(monkeypatch):
    monkeypatch.setenv("WEATHER_ENABLED", "false")
    weather = asyncio.run(WeatherService().get(Origin(latitude=51.09, longitude=71.41)))
    assert weather.status == "unavailable"
    assert weather.temperature_c is None and weather.wind_kmh is None
