import pytest
from backend.app.generation import ACTIVITIES, GeneratedResponse, validate_grounded


def payload(rec, **changes):
    item = dict(poi_id=rec.poi.id, why_suitable=rec.why_suitable,
                evidence_field_ids=rec.evidence_field_ids,
                suggested_activity=ACTIVITIES[rec.poi.category][0], caveats=[])
    item.update(changes)
    return GeneratedResponse(summary="Подобрали места по вашим условиям.", recommendations=[item])


def test_valid_response_keeps_only_evidence(recommendation_factory):
    rec = recommendation_factory()
    assert validate_grounded(payload(rec), [rec]).recommendations[0].poi_id == rec.poi.id


@pytest.mark.parametrize("changes", [
    {"poi_id": "invented:999"},
    {"evidence_field_ids": ["attributes.sockets"]},
    {"why_suitable": "Здесь есть бесплатный Wi-Fi и розетки."},
    {"suggested_activity": "Поднимитесь на закрытую крышу."},
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
