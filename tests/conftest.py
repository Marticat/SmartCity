"""Small synthetic fixtures used only by tests; never copied into demo data."""
from datetime import datetime, timezone
import pytest
from backend.app.schemas.models import POI, Recommendation


@pytest.fixture
def instant():
    return datetime(2026, 10, 20, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def poi_factory():
    def make(**changes):
        row = dict(
            id="test:1", source_id="node/1",
            source_url="https://www.openstreetmap.org/node/1",
            name="TEST ONLY", latitude=51.09, longitude=71.41,
            coordinate_kind="node", category="cafe", description="Кафе.",
            collected_at="2026-10-20T07:00:00+00:00",
            source_updated_at="2026-10-20T07:00:00+00:00", content_hash="fixture",
            attributes={"indoor": None, "wifi": None, "sockets": None, "wheelchair": None, "free": None},
            field_provenance={"category": {"source_url": "https://www.openstreetmap.org/node/1"}},
        )
        row.update(changes)
        return POI(**row)
    return make


@pytest.fixture
def recommendation_factory(poi_factory):
    def make(**changes):
        fields = dict(
            poi=poi_factory(), why_suitable="Категория соответствует запросу.",
            evidence_field_ids=["category"], suggested_activity="Сделайте паузу.",
            distance_m=100, visit_minutes_min=15, visit_minutes_max=30,
            maps_url="https://www.openstreetmap.org/node/1",
        )
        fields.update(changes)
        return Recommendation(**fields)
    return make
