# QADAM API v1

Canonical Pydantic models: `backend/app/schemas/models.py`. JSON uses snake_case.
Backend owns implementation and may extend optional fields; breaking changes require coordination.

- `GET /health`: `{status:"ok", dataset_ready:boolean, semantic_ready:boolean, llm_configured:boolean}`
- `GET /api/dataset/status`: DatasetStatus below.
- `GET /api/locations/search?q=...&limit=8`: `{locations: Location[]}`. Empty q returns dataset landmarks.
- `GET /api/pois/{id}`: full POI.
- `POST /api/recommend`: RecommendRequest -> RecommendResponse below.
- validation: HTTP 422; provider failure returns honest degraded response where possible.

No precise user location in GET URLs. No search history persisted.

## Request
`query` string <=1000; `origin` `{latitude,longitude,label?}` or null;
`time_budget_minutes` integer 10..180 (default 60);
`preset` walk|coffee|family|indoor; `return_to_start` bool;
`constraints` `{indoor_only, wheelchair_required, wifi_required, sockets_required, free_only, open_now}` booleans;
`less_outdoors` bool; `excluded_poi_ids` string[];
`visit_datetime` ISO timezone-aware string or null.
The UI offers optional Astana local date/time and sends an explicit `+05:00` offset.
Night/evening requests without `visit_datetime` return a clarification instead of
applying daytime opening hours. Explicit text and UI time budgets use the smaller value.

## Response
`request_id`, `mode`: rag|search_only|lexical_only|test;
`summary`, `recommendations`: Recommendation[];
`clarifying_question`: string|null; `warnings`: string[];
`trace`: `{candidate_count, filtered_count, retrieval_method, applied_constraints:string[], sources:string[], elapsed_ms}`;
`weather`: `{status: available|unavailable, temperature_c:number|null, wind_kmh:number|null, observed_at:string|null, source_url:string|null}`;
`dataset`: DatasetStatus.

Recommendation: `poi`: POI; `why_suitable`, `evidence_field_ids`: string[];
`suggested_activity`, `activity_origin`: ai|template;
`distance_m`: number; `distance_method`: straight_line|walking;
`walking_minutes`: number|null; `visit_minutes_min`, `visit_minutes_max`;
`total_minutes`: number|null; `opening_status`: open|closed|unknown;
`caveats`: string[]; `maps_url`: safe OSM URL.

DatasetStatus: `ready`, `poi_count`, `collected_at`: string|null, `checksum`: string|null,
`semantic_ready`, `embedding_model`: string|null, `stale`, `source`, `coverage`: object.

Location: `id`, `name`, `latitude`, `longitude`, `category`.
POI minimally: `id`, `name`, `latitude`, `longitude`, `category`, `source_url`,
`address`: string|null, `description`, `description_origin`, `coordinate_kind`,
`opening_hours_raw`: string|null, `collected_at`, `source_updated_at`: string|null,
`attributes`: Record<string,bool|null>, `field_provenance`: object, `tags`: object.

`description_origin=official_source_summary` identifies reviewed enrichment.
`field_provenance.description` includes `source_url`, `source_name`, `collected_at`,
`method`, and `value`; the POI's main `source_url` still identifies its OSM record.
Additional `attributes.interactive` and `attributes.quiet` use the same tri-state
and evidence rules. Their explicit mandatory text requirements are parsed server-side.

In `rag` mode, `why_suitable` and `suggested_activity` are generated and validated.
Facts in the generator's internal contract use server-rendered slots; that internal
syntax is never exposed in this API. `activity_origin=ai` distinguishes generated
ideas even when embeddings are unavailable and the response mode is `lexical_only`.
All mandatory server caveats are retained. Structural validation and a second model
review are risk reductions, not a proof that free prose can never contain errors.
