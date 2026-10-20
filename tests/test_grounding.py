import asyncio
import json
from types import SimpleNamespace
import pytest
from backend.app.generation import (ACTIVITIES, GeneratedResponse, GroundingReview, GeminiGenerator,
                                    fact_catalog, sanitized_context, validate_grounded, validate_review)
from backend.app.constraints import parse_intent
from backend.app.schemas.models import RecommendRequest, Origin


def payload(rec, **changes):
    item = dict(poi_id=rec.poi.id, why_suitable="Для короткой остановки можно выбрать это место: {{category}}.",
                evidence_field_ids=rec.evidence_field_ids,
                suggested_activity=ACTIVITIES[rec.poi.category][0], caveats=[])
    item.update(changes)
    return GeneratedResponse(summary="Подобрали места по вашим условиям.", recommendations=[item])


def test_valid_response_keeps_only_evidence(recommendation_factory):
    rec = recommendation_factory()
    assert validate_grounded(payload(rec), [rec]).recommendations[0].poi_id == rec.poi.id


def test_free_paraphrase_is_rendered_without_placeholders(recommendation_factory):
    rec = recommendation_factory()
    result = validate_grounded(payload(rec, why_suitable="Для смены обстановки подойдёт {{category}}. От старта — {{distance}}; {{visit}}.",
        suggested_activity="Попробуйте записать три впечатления от прогулки и обсудить их за столом."), [rec])
    text = result.recommendations[0].why_suitable
    assert text != rec.why_suitable and "{{" not in text
    assert "кафе" in text and "до 500 м по прямой" in text and "15–30 мин" in text
    assert "три впечатления" in result.recommendations[0].suggested_activity


@pytest.mark.parametrize("changes", [
    {"poi_id": "invented:999"},
    {"evidence_field_ids": ["attributes.sockets"]},
    {"why_suitable": "Здесь есть бесплатный Wi-Fi и розетки."},
    {"suggested_activity": "Поднимитесь на закрытую крышу."},
    {"why_suitable": "Это место: {{attributes.wifi}}."},
    {"why_suitable": "Это {{category}}, до него ровно 300 метров."},
    {"why_suitable": "Здесь {{category}} и безопасная дорога."},
    {"evidence_field_ids": ["category", "name"]},
    {"caveats": ["Скидка 50% по промокоду"]},
])
def test_fabricated_facts_and_unknown_places_are_rejected(changes, recommendation_factory):
    rec = recommendation_factory()
    with pytest.raises(ValueError):
        validate_grounded(payload(rec, **changes), [rec])


def test_unsafe_summary_does_not_bypass_validation(recommendation_factory):
    rec = recommendation_factory()
    result = payload(rec)
    result.summary = "Все места безопасны ночью и точно открыты."
    with pytest.raises(ValueError):
        validate_grounded(result, [rec])


def test_duplicate_id_is_rejected(recommendation_factory):
    rec = recommendation_factory()
    result = payload(rec)
    result.recommendations.append(result.recommendations[0])
    with pytest.raises(ValueError):
        validate_grounded(result, [rec])


def test_official_description_requires_provenance_and_origin(recommendation_factory):
    rec = recommendation_factory()
    rec.poi.description = "В музее есть интерактивные киоски; один зал закрыт."
    assert "description" not in fact_catalog(rec)
    rec.poi.description_origin = "official_source_summary"
    rec.poi.field_provenance["description"] = {"source_url": "https://example.org"}
    result = validate_grounded(payload(rec, why_suitable="Для интереса к истории: {{description}}.",
                                      evidence_field_ids=["description"]), [rec])
    assert "один зал закрыт" in result.recommendations[0].why_suitable


def test_context_drops_raw_query_origin_and_unrecognized_preferences(recommendation_factory):
    query = "Мне тихое кафе, мой адрес SECRET_ADDRESS, телефон SECRET_PHONE"
    intent = parse_intent(RecommendRequest(query=query, origin=Origin(latitude=51.09123456, longitude=71.41987654, label="SECRET_LABEL")))
    intent.interests.append("SECRET_PHONE")
    intent.soft_preferences.append("SECRET_ADDRESS")
    context = json.dumps(sanitized_context([recommendation_factory(distance_m=437.12345)], intent), ensure_ascii=False)
    assert "quiet" in context
    for secret in ("SECRET_", "51.09123456", "71.41987654", "437.12345", "437", query):
        assert secret not in context
    assert "до 500 м" in context


def test_semantic_reviewer_rejects_subtle_unsupported_atmosphere(recommendation_factory):
    rec = recommendation_factory()
    # Local rules do not pretend to understand every factual paraphrase.
    rendered = validate_grounded(payload(rec, why_suitable="Здесь {{category}}, где царит уединённая атмосфера."), [rec])
    review = GroundingReview(all_claims_supported=False, activities_are_only_suggestions=True,
        constraints_preserved=True, reviewed_poi_ids=[rec.poi.id], issues=["Atmosphere unsupported"])
    with pytest.raises(ValueError):
        validate_review(review, rendered)


def test_review_must_cover_all_selected_places(recommendation_factory):
    rec = recommendation_factory()
    rendered = validate_grounded(payload(rec), [rec])
    review = GroundingReview(all_claims_supported=True, activities_are_only_suggestions=True,
        constraints_preserved=True, reviewed_poi_ids=[], issues=[])
    with pytest.raises(ValueError):
        validate_review(review, rendered)


def test_provider_prose_is_reviewed_then_delivered(monkeypatch, recommendation_factory):
    from google import genai
    rec = recommendation_factory()
    calls = []
    answers = [
        payload(rec).model_dump_json(),
        GroundingReview(all_claims_supported=True, activities_are_only_suggestions=True,
                        constraints_preserved=True, reviewed_poi_ids=[rec.poi.id]).model_dump_json(),
    ]
    class Client:
        def __init__(self, **kwargs): self.aio = self; self.models = self
        async def __aenter__(self): return self
        async def __aexit__(self, *args): calls.append("closed")
        async def generate_content(self, **kwargs):
            calls.append(kwargs["config"].response_json_schema)
            return SimpleNamespace(text=answers.pop(0))
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setattr(genai, "Client", Client)
    result, warning = asyncio.run(GeminiGenerator().generate([rec], parse_intent(RecommendRequest(query="кофе"))))
    assert warning is None and "{{" not in result.recommendations[0].why_suitable
    assert calls == [GeneratedResponse.model_json_schema(), GroundingReview.model_json_schema(), "closed"]


def test_repeated_reviewer_rejection_falls_back(monkeypatch, recommendation_factory):
    from google import genai
    rec = recommendation_factory()
    calls = []
    class Client:
        def __init__(self, **kwargs): self.aio = self; self.models = self
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def generate_content(self, **kwargs):
            schema = kwargs["config"].response_json_schema
            calls.append(schema)
            body = payload(rec) if schema == GeneratedResponse.model_json_schema() else GroundingReview(
                all_claims_supported=False, activities_are_only_suggestions=True,
                constraints_preserved=True, reviewed_poi_ids=[rec.poi.id], issues=["unsupported"])
            return SimpleNamespace(text=body.model_dump_json())
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setattr(genai, "Client", Client)
    result, warning = asyncio.run(GeminiGenerator().generate([rec], parse_intent(RecommendRequest())))
    assert result is None and "не прошёл" in warning
    assert len(calls) == 4
