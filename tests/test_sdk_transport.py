"""Exercise actual installed Gemini SDK serialization with an offline HTTP transport.

This checks wire/schema integration, not live provider access or LLM quality.
"""
import asyncio
import json

import httpx
from google import genai

from backend.app.constraints import parse_intent
from backend.app.generation import GeminiGenerator
from backend.app.schemas.models import RecommendRequest


def test_real_sdk_serializes_both_schemas_and_parses_responses(monkeypatch, recommendation_factory):
    rec = recommendation_factory()
    answers = [
        {"summary": "Подобрали вариант для небольшой остановки.", "recommendations": [{
            "poi_id": rec.poi.id, "why_suitable": "Для короткой остановки подойдёт {{category}}.",
            "evidence_field_ids": ["category"],
            "suggested_activity": "Попробуйте записать впечатления от прогулки.", "caveats": [],
        }], "clarifying_question": None},
        {"all_claims_supported": True, "activities_are_only_suggestions": True,
         "constraints_preserved": True, "reviewed_poi_ids": [rec.poi.id], "issues": []},
    ]
    requests = []

    async def respond(request):
        body = json.loads(request.content)
        assert request.method == "POST"
        assert ":generateContent" in request.url.path
        config = body["generationConfig"]
        assert config["responseMimeType"] == "application/json"
        assert "properties" in config["responseSchema"]
        requests.append(body)
        answer = answers.pop(0)
        return httpx.Response(200, json={"candidates": [{
            "content": {"role": "model", "parts": [{"text": json.dumps(answer, ensure_ascii=False)}]},
            "finishReason": "STOP",
        }]})

    original_client = genai.Client

    def offline_client(**kwargs):
        kwargs["http_options"] = kwargs["http_options"].model_copy(update={
            "httpx_async_client": httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        })
        return original_client(**kwargs)

    monkeypatch.setenv("GEMINI_API_KEY", "test-only-never-sent-to-network")
    monkeypatch.setattr(genai, "Client", offline_client)
    result, warning = asyncio.run(GeminiGenerator().generate(
        [rec], parse_intent(RecommendRequest(query="кофе"))))
    assert warning is None
    assert result is not None and len(requests) == 2 and not answers
    assert "{{" not in result.recommendations[0].why_suitable
