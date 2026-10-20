"""Verify the public response consumes validated generated fields, without a key."""
import asyncio
from types import SimpleNamespace
from backend.app.schemas.models import DatasetStatus, RecommendRequest, Origin, Weather
from backend.app.generation import GeneratedResponse
import backend.app.main as server


def test_generated_reason_evidence_and_activity_reach_response(monkeypatch, poi_factory):
    place = poi_factory()
    place.description_origin = "official_source_summary"
    place.description = "Официальное короткое описание."
    place.field_provenance["description"] = {"source_url": "https://example.org"}
    fake_store = SimpleNamespace(pois=[place], semantic_ready=True,
        status=lambda: DatasetStatus(ready=True, poi_count=1, semantic_ready=True),
        search=lambda *args: [(place, 0.03)])
    class WeatherService:
        async def get(self, *args): return Weather()
    class Routing:
        async def route(self, *args): return None
    class Generator:
        configured = True
        async def generate(self, candidates, intent):
            assert "Официальное короткое описание" in candidates[0].why_suitable
            assert "description" in candidates[0].evidence_field_ids
            return GeneratedResponse(summary="Можно начать с небольшой остановки.", recommendations=[{
                "poi_id": place.id, "why_suitable": "Новое объяснение ИИ по официальному описанию.",
                "evidence_field_ids": ["description"], "suggested_activity": "Попробуйте записать впечатления от прогулки.",
                "caveats": []}]), None
    monkeypatch.setattr(server, "store", fake_store)
    monkeypatch.setattr(server, "weather_service", WeatherService())
    monkeypatch.setattr(server, "routing_service", Routing())
    monkeypatch.setattr(server, "generator", Generator())
    result = asyncio.run(server.recommend_impl(RecommendRequest(origin=Origin(latitude=51.09, longitude=71.41))))
    rec = result.recommendations[0]
    assert rec.why_suitable.startswith("Новое объяснение")
    assert rec.evidence_field_ids == ["description"] and rec.activity_origin == "ai"
    assert any("Путь и время" in text for text in rec.caveats)
    assert "https://example.org" in result.trace.sources
