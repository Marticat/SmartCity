import pytest
from backend.app.constraints import haversine_m, opening_status, parse_intent, filter_candidates
from backend.app.schemas.models import RecommendRequest, Origin, Constraints


def request(**changes):
    return RecommendRequest(origin=Origin(latitude=51.09, longitude=71.41), **changes)


def test_geography_order_and_distance():
    assert haversine_m(51.09, 71.41, 51.09, 71.41) == 0
    assert 1100 < haversine_m(51.09, 71.41, 51.10, 71.41) < 1125
    assert 690 < haversine_m(51.09, 71.41, 51.09, 71.42) < 710


@pytest.mark.parametrize("raw", [None, "PH off", "Mo-Fr sunrise-sunset", "22:00-03:00", "25:00-26:00"])
def test_unknown_or_unsupported_hours_not_open(raw, instant):
    assert opening_status(raw, instant) == "unknown"


def test_place_closing_during_visit_is_not_available(instant):
    # Fixed Tuesday 12:00 in Astana; a 30-minute visit crosses closing.
    assert opening_status("Tu 10:00-12:15", instant, visit_minutes=30) == "closed"
    assert opening_status("Tu 10:00-13:00", instant, visit_minutes=30) == "open"


def test_stale_hours_are_unknown(instant):
    assert opening_status("24/7", instant, "2020-01-01T00:00:00+00:00") == "unknown"


def test_explicit_negation_overrides_preset():
    intent = parse_intent(request(query="Не кафе, хочу парк", preset="coffee"))
    assert intent.desired_categories == ["park"]
    assert "cafe" in intent.excluded_categories
    assert intent.conflicts


@pytest.mark.parametrize("attribute,constraint", [
    ("indoor", "indoor_only"), ("wifi", "wifi_required"),
    ("sockets", "sockets_required"), ("wheelchair", "wheelchair_required"), ("free", "free_only"),
])
def test_unknown_attribute_cannot_satisfy_hard_constraint(attribute, constraint, poi_factory, instant):
    req = request(constraints=Constraints(**{constraint: True}))
    unknown = poi_factory(id="test:unknown")
    confirmed = poi_factory(id="test:confirmed", attributes={attribute: True})
    matched = filter_candidates([unknown, confirmed], req, parse_intent(req), instant)
    assert [p.id for p, _, _ in matched] == ["test:confirmed"]


def test_return_to_start_doubles_travel_lower_bound(poi_factory, instant):
    # ~700 m, 5 min visit + 5 min margin: one-way fits 20; return does not.
    poi = poi_factory(category="artwork", longitude=71.42)
    outbound = request(time_budget_minutes=20)
    returning = request(time_budget_minutes=20, return_to_start=True)
    assert filter_candidates([poi], outbound, parse_intent(outbound), instant)
    assert not filter_candidates([poi], returning, parse_intent(returning), instant)


def test_out_of_coverage_is_not_silently_moved(poi_factory, instant):
    req = RecommendRequest(origin=Origin(latitude=43.24, longitude=76.92))
    assert filter_candidates([poi_factory()], req, parse_intent(req), instant) == []


@pytest.mark.parametrize("query", ["Два часа до вылета", "Ночью на секретную крышу"])
def test_risky_context_requests_clarification(query):
    assert parse_intent(request(query=query)).clarification


def test_below_supported_text_budget_is_not_silently_expanded():
    intent = parse_intent(request(query="У меня 5 минут"))
    assert intent.time_budget_minutes <= 5 or intent.clarification


def test_negated_service_is_not_required():
    intent = parse_intent(request(query="Кофе, розетка не нужна"))
    assert not intent.hard_constraints.sockets_required


def test_weekday_exception_does_not_claim_open(instant):
    monday = instant.replace(day=19)
    assert opening_status("Mo-Fr 09:00-18:00; Mo off", monday) != "open"
