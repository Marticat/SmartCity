"""Full API pipeline using an explicitly synthetic temporary SQLite dataset."""
import json
import sqlite3
from fastapi.testclient import TestClient
from backend.app.data import digest, document
from backend.app.retrieval import Store
from backend.app.schemas.models import Weather
import backend.app.main as server


class OfflineWeather:
    async def get(self, *args):
        return Weather()


class NoRoute:
    async def route(self, *args):
        return None


class NoGenerator:
    configured = False
    async def generate(self, *args):
        return None, "ТЕСТ: внешняя генерация отключена."


def make_client(tmp_path, monkeypatch, poi_factory):
    pois = [poi_factory(id="test:park", name="TEST PARK", category="park", attributes={"indoor": False}),
            poi_factory(id="test:cafe", name="TEST CAFE", category="cafe"),
            poi_factory(id="test:far", name="TEST FAR PARK", category="park", latitude=51.22)]
    rows = [p.model_dump(mode="json") for p in pois]
    for folder in ("processed", "manifests", "index"):
        (tmp_path / folder).mkdir()
    (tmp_path / "processed/pois.json").write_text(json.dumps(rows), encoding="utf-8")
    (tmp_path / "manifests/collection.json").write_text(json.dumps({"collected_at": "2026-10-20T07:00:00+00:00", "checksum": digest(rows)}), encoding="utf-8")
    with sqlite3.connect(tmp_path / "index/pois.sqlite") as db:
        db.execute("CREATE VIRTUAL TABLE poi_fts USING fts5(poi_id UNINDEXED, content)")
        db.executemany("INSERT INTO poi_fts VALUES (?, ?)", [(p.id, document(p)) for p in pois])
    store = Store(tmp_path)
    monkeypatch.setattr(server, "store", store)
    monkeypatch.setattr(server, "weather_service", OfflineWeather())
    monkeypatch.setattr(server, "routing_service", NoRoute())
    monkeypatch.setattr(server, "generator", NoGenerator())
    server.rate_windows.clear()
    return TestClient(server.app), store


def test_pipeline_applies_geography_and_negation_before_topk(tmp_path, monkeypatch, poi_factory):
    client, store = make_client(tmp_path, monkeypatch, poi_factory)
    response = client.post("/api/recommend", json={"query": "Не кафе, хочу парк", "origin": {"latitude": 51.09, "longitude": 71.41}, "time_budget_minutes": 30,
                                                 "visit_datetime": "2026-10-20T12:00:00+05:00"})
    assert response.status_code == 200
    body = response.json()
    assert [r["poi"]["id"] for r in body["recommendations"]] == ["test:park"]
    rec = body["recommendations"][0]
    assert rec["distance_method"] == "straight_line"
    assert rec["walking_minutes"] is None and rec["total_minutes"] is None
    assert rec["opening_status"] == "unknown"
    assert body["mode"] == "lexical_only"
    assert body["weather"]["status"] == "unavailable"
    assert body["trace"]["filtered_count"] == 1
    assert store.lexical('park " OR * --')  # Safe token construction, no SQL injection.


def test_strict_sockets_does_not_return_unknown(tmp_path, monkeypatch, poi_factory):
    client, _ = make_client(tmp_path, monkeypatch, poi_factory)
    result = client.post("/api/recommend", json={"query": "Кофе с обязательной розеткой", "origin": {"latitude": 51.09, "longitude": 71.41}}).json()
    assert result["recommendations"] == []
    assert result["warnings"]


def test_missing_origin_asks_one_question(tmp_path, monkeypatch, poi_factory):
    client, _ = make_client(tmp_path, monkeypatch, poi_factory)
    result = client.post("/api/recommend", json={"query": "Погулять"}).json()
    assert result["recommendations"] == []
    assert result["clarifying_question"]


def test_outside_area_and_invalid_coordinates(tmp_path, monkeypatch, poi_factory):
    client, _ = make_client(tmp_path, monkeypatch, poi_factory)
    response = client.post("/api/recommend", json={"origin": {"latitude": 43.2, "longitude": 76.9}})
    assert response.json()["recommendations"] == []
    assert response.json()["clarifying_question"]
    assert client.post("/api/recommend", json={"origin": {"latitude": 500, "longitude": 71}}).status_code == 422


def test_local_search_and_missing_poi(tmp_path, monkeypatch, poi_factory):
    client, _ = make_client(tmp_path, monkeypatch, poi_factory)
    assert client.get("/api/locations/search", params={"q": "TEST PARK"}).status_code == 200
    assert client.get("/api/pois/does-not-exist").status_code == 404


def test_confirmed_strong_wind_promotes_evidenced_indoor(tmp_path, monkeypatch, poi_factory):
    client, store = make_client(tmp_path, monkeypatch, poi_factory)
    museum = poi_factory(id="test:indoor", name="TEST INDOOR", category="museum",
                         attributes={"indoor": True}, longitude=71.411,
                         field_provenance={"category": {}, "attributes.indoor": {}})
    store.pois.append(museum)
    store.by_id[museum.id] = museum
    class Wind:
        async def get(self, *args):
            return Weather(status="available", wind_kmh=45, temperature_c=-2,
                           observed_at="2026-10-20T07:00:00+00:00", source_url="https://open-meteo.com/")
    monkeypatch.setattr(server, "weather_service", Wind())
    result = client.post("/api/recommend", json={"preset":"family","time_budget_minutes":45,
        "origin":{"latitude":51.09,"longitude":71.41},
        "visit_datetime":"2026-10-20T12:00:00+05:00"}).json()
    assert result["weather"]["wind_kmh"] == 45
    assert result["recommendations"][0]["poi"]["id"] == "test:indoor"
    assert any("ветер" in warning for warning in result["warnings"])
