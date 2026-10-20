import json
from datetime import datetime, timezone

import httpx
import pytest

from backend.app.data import normalize_elements
from backend.app.enrichment import apply_enrichment
from scripts.check_sources import check_record, checked_url

NOW = datetime(2026, 10, 20, 13, tzinfo=timezone.utc)


def inputs(tmp_path, **updates):
    pois, _ = normalize_elements([{
        "type": "node", "id": 1, "lat": 51.1, "lon": 71.4,
        "tags": {"tourism": "museum", "name": "TEST MUSEUM"},
    }], NOW.isoformat())
    record = {
        "poi_id": "osm:node:1", "expected_category": "museum", "expected_name": "TEST MUSEUM",
        "source_url": "https://nmrk.kz/example", "source_name": "TEST SOURCE",
        "reviewed_at": NOW.isoformat(), "description": "Тестовое описание для проверки привязки факта.",
        "attributes": {"interactive": True},
    }
    record.update(updates)
    path = tmp_path / "enrichment.json"
    path.write_text(json.dumps({"schema_version": 1, "records": [record]}), encoding="utf-8")
    return pois, path


def test_reviewed_facts_have_their_own_source_and_do_not_mutate_raw_pois(tmp_path):
    pois, path = inputs(tmp_path, alternative_names=["National test museum"])
    enriched, audit = apply_enrichment(pois, path, as_of=NOW)
    assert audit["applied"] == 1
    assert enriched[0].attributes["interactive"] is True
    assert enriched[0].field_provenance["attributes.interactive"]["source_url"] == "https://nmrk.kz/example"
    assert enriched[0].description_origin == "official_source_summary"
    assert pois[0].description_origin == "derived_from_tags"
    assert enriched[0].content_hash != pois[0].content_hash
    assert enriched[0].source_url == pois[0].source_url
    assert enriched[0].alternative_names == ["National test museum"]
    assert enriched[0].field_provenance["alternative_names"]["value"] == ["National test museum"]


@pytest.mark.parametrize("updates,reason", [
    ({"expected_name": "OTHER PLACE"}, "identity_changed_requires_review"),
    ({"reviewed_at": "2025-01-01T00:00:00+00:00"}, "review_expired_or_in_future"),
    ({"reviewed_at": "2027-01-01T00:00:00+00:00"}, "review_expired_or_in_future"),
])
def test_changed_identity_or_stale_source_cannot_confirm_facts(tmp_path, updates, reason):
    pois, path = inputs(tmp_path, **updates)
    enriched, audit = apply_enrichment(pois, path, as_of=NOW)
    assert audit["applied"] == 0
    assert audit["skipped"][0]["reason"] == reason
    assert enriched[0].attributes.get("interactive") is None


def test_conflicting_sources_require_review(tmp_path):
    pois, path = inputs(tmp_path)
    pois[0].attributes["interactive"] = False
    enriched, audit = apply_enrichment(pois, path, as_of=NOW)
    assert enriched[0].attributes["interactive"] is False
    assert audit["skipped"][0]["reason"] == "conflicting_source_attribute"


@pytest.mark.parametrize("url", ["http://nmrk.kz", "https://127.0.0.1", "https://nmrk.kz.evil.test", "https://u:p@nmrk.kz", "https://nmrk.kz:8443"])
def test_source_checker_has_a_fixed_public_allowlist(url):
    with pytest.raises(ValueError):
        checked_url(url)


def test_source_checker_does_not_treat_scripts_as_factual_content():
    record = {"poi_id": "test", "source_url": "https://nmrk.kz/example",
              "reviewed_at": NOW.isoformat(), "check_terms": ["touch-screen"]}
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, headers={"content-type": "text/html"}, text="<p>Museum</p><script>touch-screen</script>"))
    with httpx.Client(transport=transport) as client:
        result = check_record(client, record)
    assert result["status"] == "review_needed"
    assert result["reviewed_at_unchanged"] == NOW.isoformat()
