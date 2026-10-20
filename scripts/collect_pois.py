"""Batch only: python -m scripts.collect_pois [--refresh|--normalize-only|--validate]."""
import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
import httpx
from backend.app.config import BBOX, DATA_DIR, USER_AGENT
from backend.app.data import atomic_json, digest, normalize_elements
from backend.app.schemas.models import POI

ENDPOINT = "https://overpass-api.de/api/interpreter"
QUERY = f"""[out:json][timeout:120];
(
 nwr["amenity"~"^(cafe|theatre)$"]({','.join(map(str, BBOX))});
 nwr["leisure"~"^(park|playground)$"]({','.join(map(str, BBOX))});
 nwr["tourism"~"^(museum|gallery|viewpoint|attraction|artwork)$"]({','.join(map(str, BBOX))});
);
out meta center;"""


def collect(refresh=False, normalize_only=False, validate=False):
    rawpath = DATA_DIR / "raw" / "overpass_astana.json"
    if validate:
        rows = json.loads((DATA_DIR / "processed" / "pois.json").read_text(encoding="utf-8"))
        for row in rows:
            POI.model_validate(row)
        assert len({r["id"] for r in rows}) == len(rows), "Duplicate identities"
        manifest = json.loads((DATA_DIR / "manifests" / "collection.json").read_text(encoding="utf-8"))
        assert digest(rows) == manifest["checksum"], "Manifest checksum mismatch"
        print(json.dumps({"valid_pois": len(rows), "checksum": digest(rows)}))
        return
    if normalize_only and not rawpath.exists():
        raise RuntimeError("No raw snapshot exists; run collection first")
    if rawpath.exists() and (normalize_only or not refresh):
        raw = json.loads(rawpath.read_text(encoding="utf-8"))
        collected = json.loads((DATA_DIR / "manifests" / "collection.json").read_text(encoding="utf-8"))["collected_at"] if (DATA_DIR / "manifests" / "collection.json").exists() else datetime.now(timezone.utc).isoformat()
    else:
        for attempt in range(3):
            try:
                response = httpx.post(ENDPOINT, data={"data": QUERY}, headers={"User-Agent": USER_AGENT}, timeout=150)
                response.raise_for_status()
                raw = response.json()
                if raw.get("remark") or not raw.get("elements"):
                    raise ValueError("Incomplete or empty Overpass response; previous snapshot retained")
                collected = datetime.now(timezone.utc).isoformat()
                break
            except (httpx.HTTPError, ValueError) as error:
                if attempt == 2:
                    raise RuntimeError("Collection failed; previous snapshot retained") from error
                time.sleep(15 * (attempt + 1))
        # Validate normalization before replacing any successful raw snapshot.
    pois, reasons = normalize_elements(raw["elements"], collected)
    if not pois:
        raise RuntimeError("No usable records; previous snapshot retained")
    rows = [p.model_dump(mode="json") for p in pois]
    quality = {"categories": dict(Counter(p.category for p in pois)), "opening_hours": sum(bool(p.opening_hours_raw) for p in pois), "address": sum(bool(p.address) for p in pois), "source_description": 0, "derived_description": len(pois), "known_attributes": {k: sum(p.attributes.get(k) is not None for p in pois) for k in ("indoor", "wifi", "sockets", "wheelchair", "free")}}
    manifest = {"collected_at": collected, "source": "OpenStreetMap / Overpass API", "source_url": ENDPOINT, "license": "ODbL 1.0", "attribution": "© OpenStreetMap contributors", "area": {"kind": "demo_bounding_box", "bbox_south_west_north_east": BBOX, "description": "Central Astana and EXPO demo rectangle; not an administrative boundary"}, "query": QUERY, "raw_count": len(raw["elements"]), "accepted_count": len(pois), "rejected_count": sum(reasons.values()), "rejection_reasons": reasons, "checksum": digest(rows), "raw_checksum": digest(raw), "source_base_timestamp": raw.get("osm3s", {}).get("timestamp_osm_base"), "quality": quality}
    atomic_json(rawpath, raw)
    atomic_json(DATA_DIR / "processed" / "pois.json", rows)
    atomic_json(DATA_DIR / "manifests" / "collection.json", manifest)
    atomic_json(DATA_DIR / "processed" / "quality.json", quality)
    print(json.dumps({"accepted": len(pois), "raw": len(raw["elements"]), "rejected": reasons, "quality": quality}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--normalize-only", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    collect(args.refresh, args.normalize_only, args.validate)
