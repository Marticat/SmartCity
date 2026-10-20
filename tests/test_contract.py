from datetime import datetime
import pytest
from pydantic import ValidationError
from backend.app.schemas.models import Origin, RecommendRequest


@pytest.mark.parametrize("lat,lon", [(91, 71), (51, 181), (float("nan"), 71), (float("inf"), 71)])
def test_coordinates_reject_invalid_values(lat, lon):
    with pytest.raises(ValidationError):
        Origin(latitude=lat, longitude=lon)


@pytest.mark.parametrize("minutes", [0, 9, 181, -30])
def test_time_budget_has_real_bounds(minutes):
    with pytest.raises(ValidationError):
        RecommendRequest(time_budget_minutes=minutes)


def test_visit_datetime_requires_timezone():
    with pytest.raises(ValidationError):
        RecommendRequest(visit_datetime=datetime(2026, 10, 20, 12))


def test_missing_origin_is_valid_for_clarification():
    assert RecommendRequest(query="Где погулять?").origin is None
