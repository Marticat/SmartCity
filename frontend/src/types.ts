/** API v1. Canonical schemas: backend/app/schemas/models.py. */
export interface Origin { latitude: number; longitude: number; label?: string }
export interface Location extends Origin { id: string; name: string; category: string }
export type Preset = 'walk' | 'coffee' | 'family' | 'indoor'
export interface Constraints {
  indoor_only: boolean; wheelchair_required: boolean; wifi_required: boolean;
  sockets_required: boolean; free_only: boolean; open_now: boolean;
}
export interface RecommendRequest {
  query: string; origin: Origin | null; time_budget_minutes: number; preset: Preset;
  return_to_start: boolean; constraints: Constraints; less_outdoors: boolean;
  excluded_poi_ids: string[]; visit_datetime: string | null;
}
export interface POI extends Origin {
  id: string; name: string; category: string; source_url: string; address: string | null;
  description: string; description_origin: string; coordinate_kind: string;
  opening_hours_raw: string | null; collected_at: string; source_updated_at: string | null;
  attributes: Record<string, boolean | null>; field_provenance: Record<string, unknown>;
  tags: Record<string, string>;
}
export interface DatasetStatus {
  ready: boolean; poi_count: number; collected_at: string | null; checksum: string | null;
  semantic_ready: boolean; embedding_model: string | null; stale: boolean; source: string;
  coverage: Record<string, unknown>;
}
export interface Recommendation {
  poi: POI; why_suitable: string; evidence_field_ids: string[]; suggested_activity: string;
  activity_origin: 'ai' | 'template'; distance_m: number; distance_method: 'straight_line' | 'walking';
  walking_minutes: number | null; visit_minutes_min: number; visit_minutes_max: number;
  total_minutes: number | null; opening_status: 'open' | 'closed' | 'unknown';
  caveats: string[]; maps_url: string;
}
export interface RecommendResponse {
  request_id: string; mode: 'rag' | 'search_only' | 'lexical_only' | 'test'; summary: string;
  recommendations: Recommendation[]; clarifying_question: string | null; warnings: string[];
  trace: { candidate_count: number; filtered_count: number; retrieval_method: string;
    applied_constraints: string[]; sources: string[]; elapsed_ms: number };
  weather: { status: 'available' | 'unavailable'; temperature_c: number | null;
    wind_kmh: number | null; observed_at: string | null; source_url: string | null };
  dataset: DatasetStatus;
}
