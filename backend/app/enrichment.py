"""Apply reviewed, field-cited facts offline; never infer amenities from categories."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .data import digest, safe_url

ALLOWED_ATTRIBUTES = {"indoor", "interactive", "wifi", "sockets", "wheelchair", "free", "quiet"}
MAX_REVIEW_AGE_DAYS = 180


def apply_enrichment(pois, path: Path, *, as_of=None):
    """Return fresh POI copies and an audit; fail closed on mismatches or stale reviews.

    Summaries are reviewed source material, not automatically extracted claims.
    Checking that a page still contains a word does not renew that review.
    """
    if not path.exists():
        return pois, {"applied": 0, "skipped": [], "method": "no_reviewed_enrichment"}
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if bundle.get("schema_version") != 1:
        raise ValueError("Unsupported enrichment schema")
    as_of = as_of or datetime.now(timezone.utc)
    by_id = {p.id: p.model_copy(deep=True) for p in pois}
    seen, skipped, applied = set(), [], []
    for record in bundle["records"]:
        identity = record["poi_id"]
        if identity in seen:
            raise ValueError("Duplicate enrichment identity")
        seen.add(identity)
        poi = by_id.get(identity)
        if not poi:
            skipped.append({"poi_id": identity, "reason": "not_in_current_snapshot"})
            continue
        if (poi.category, poi.name) != (record["expected_category"], record["expected_name"]):
            skipped.append({"poi_id": identity, "reason": "identity_changed_requires_review"})
            continue
        reviewed = datetime.fromisoformat(record["reviewed_at"])
        if reviewed.tzinfo is None:
            raise ValueError("Enrichment review time needs timezone")
        if (as_of - reviewed).days > MAX_REVIEW_AGE_DAYS or reviewed > as_of:
            skipped.append({"poi_id": identity, "reason": "review_expired_or_in_future"})
            continue
        source = record["source_url"]
        if not safe_url(source) or not source.startswith("https://"):
            raise ValueError("Enrichment source must be an HTTPS page")
        description = record["description"]
        if not isinstance(description, str) or not 20 <= len(description) <= 700:
            raise ValueError("Enrichment must be a short reviewed summary")
        attrs = record.get("attributes", {})
        aliases = record.get("alternative_names", [])
        if not isinstance(aliases, list) or len(aliases) > 10 or any(not isinstance(v, str) or not 1 <= len(v) <= 150 for v in aliases):
            raise ValueError("Enrichment aliases must be short reviewed place names")
        if any(k not in ALLOWED_ATTRIBUTES or type(v) is not bool for k, v in attrs.items()):
            raise ValueError("Unsupported enrichment attribute")
        # Existing explicit source contradictions require review, not silent precedence.
        if any(poi.attributes.get(k) is not None and poi.attributes[k] != v for k, v in attrs.items()):
            skipped.append({"poi_id": identity, "reason": "conflicting_source_attribute"})
            continue
        provenance = {
            "source_url": source,
            "source_name": record["source_name"],
            "collected_at": record["reviewed_at"],
            "method": "reviewed_official_summary",
        }
        poi.description = description
        poi.description_origin = "official_source_summary"
        poi.field_provenance["description"] = {**provenance, "value": description}
        if aliases:
            poi.alternative_names = list(dict.fromkeys([*poi.alternative_names, *aliases]))
            poi.field_provenance["alternative_names"] = {**provenance, "value": aliases}
        for key, value in attrs.items():
            poi.attributes[key] = value
            poi.field_provenance[f"attributes.{key}"] = {**provenance, "value": value}
        values = poi.model_dump(mode="json")
        poi.content_hash = digest({k: v for k, v in values.items() if k not in {"collected_at", "field_provenance", "content_hash"}})
        applied.append(identity)
    return list(by_id.values()), {
        "applied": len(applied), "poi_ids": applied, "skipped": skipped,
        "bundle_checksum": digest(bundle), "review_max_age_days": MAX_REVIEW_AGE_DAYS,
        "method": "reviewed_official_summaries_applied_during_normalization",
    }
