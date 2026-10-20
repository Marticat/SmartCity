"""Shared API contract; backend owner may extend with backward-compatible fields."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class Origin(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    label: str | None = Field(default=None, max_length=200)


class Constraints(BaseModel):
    indoor_only: bool = False
    wheelchair_required: bool = False
    wifi_required: bool = False
    sockets_required: bool = False
    free_only: bool = False
    open_now: bool = False


class RecommendRequest(BaseModel):
    query: str = Field(default="", max_length=1000)
    origin: Origin | None = None
    time_budget_minutes: int = Field(default=60, ge=10, le=180)
    preset: Literal["walk", "coffee", "family", "indoor"] = "walk"
    return_to_start: bool = False
    constraints: Constraints = Field(default_factory=Constraints)
    less_outdoors: bool = False
    excluded_poi_ids: list[str] = Field(default_factory=list, max_length=100)
    visit_datetime: datetime | None = None

    @field_validator("visit_datetime")
    @classmethod
    def aware_datetime(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("visit_datetime must include a timezone")
        return value


class POI(BaseModel):
    id: str
    source: str = "OpenStreetMap"
    source_id: str
    source_url: str
    name: str
    name_ru: str | None = None
    name_kk: str | None = None
    name_en: str | None = None
    alternative_names: list[str] = Field(default_factory=list)
    latitude: float
    longitude: float
    coordinate_kind: str
    category: str
    tags: dict[str, str] = Field(default_factory=dict)
    address: str | None = None
    description: str = ""
    description_origin: str = "derived_from_tags"
    opening_hours_raw: str | None = None
    timezone: str = "Asia/Almaty"
    website: str | None = None
    public_contact: str | None = None
    attributes: dict[str, bool | None] = Field(default_factory=dict)
    field_provenance: dict[str, Any] = Field(default_factory=dict)
    source_updated_at: str | None = None
    collected_at: str
    content_hash: str


class DatasetStatus(BaseModel):
    ready: bool = False
    poi_count: int = 0
    collected_at: str | None = None
    checksum: str | None = None
    semantic_ready: bool = False
    embedding_model: str | None = None
    stale: bool = False
    source: str = "OpenStreetMap"
    coverage: dict[str, Any] = Field(default_factory=dict)


class Weather(BaseModel):
    status: Literal["available", "unavailable"] = "unavailable"
    temperature_c: float | None = None
    wind_kmh: float | None = None
    observed_at: str | None = None
    source_url: str | None = None


class Recommendation(BaseModel):
    poi: POI
    why_suitable: str
    evidence_field_ids: list[str] = Field(default_factory=list)
    suggested_activity: str
    activity_origin: Literal["ai", "template"] = "template"
    distance_m: float
    distance_method: Literal["straight_line", "walking"] = "straight_line"
    walking_minutes: float | None = None
    visit_minutes_min: int
    visit_minutes_max: int
    total_minutes: float | None = None
    opening_status: Literal["open", "closed", "unknown"] = "unknown"
    caveats: list[str] = Field(default_factory=list)
    maps_url: str


class Trace(BaseModel):
    candidate_count: int = 0
    filtered_count: int = 0
    retrieval_method: str = ""
    applied_constraints: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0


class RecommendResponse(BaseModel):
    request_id: str
    mode: Literal["rag", "search_only", "lexical_only", "test"]
    summary: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    clarifying_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    trace: Trace = Field(default_factory=Trace)
    weather: Weather = Field(default_factory=Weather)
    dataset: DatasetStatus = Field(default_factory=DatasetStatus)
