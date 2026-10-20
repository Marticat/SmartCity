"""Readiness checker safeguards; no live services or actual credentials."""
import asyncio
import json
import scripts.check_live_readiness as readiness
from scripts.check_live_readiness import check_gemini, check_ors, safe_model_name


def test_missing_keys_skip_without_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ORS_API_KEY", raising=False)
    assert asyncio.run(check_gemini()) == {
        "status":"skipped","reason":"missing_server_variable","required_variable":"GEMINI_API_KEY"}
    assert asyncio.run(check_ors()) == {
        "status":"skipped","reason":"missing_server_variable","required_variable":"ORS_API_KEY"}


def test_model_display_rejects_control_characters():
    assert safe_model_name("gemini-example") == "gemini-example"
    assert safe_model_name("bad\nHEADER: value") == "configured-model"


def test_exception_receipt_drops_provider_text_and_secrets(monkeypatch):
    async def failure():
        raise RuntimeError("Authorization: TEST_SECRET_MUST_NOT_APPEAR")
    monkeypatch.setattr(readiness,"check_gemini",failure)
    receipt = asyncio.run(readiness.run("gemini"))
    assert receipt["gemini"]["status"] == "failed"
    assert receipt["gemini"]["exception_type"] == "RuntimeError"
    assert "TEST_SECRET" not in json.dumps(receipt)
