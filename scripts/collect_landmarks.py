"""Separate local geocoding landmarks; never included in recommendation index."""
import json
import argparse
import time
from datetime import datetime, timezone
import httpx
from backend.app.config import BBOX, DATA_DIR, USER_AGENT
from backend.app.data import atomic_json, digest

QUERY = f"""[out:json][timeout:90];
nwr["name"~"EXPO|Экспо|Нұр.Әлем|Нур.Алем|Nur.Alem|MEGA.Silk.Way|Бәйтерек|Байтерек|Baiterek|Bayterek|Ботан|Botanical",i]({','.join(map(str,BBOX))});
out meta center;"""


def main(normalize_only=False):
    endpoint = "https://overpass-api.de/api/interpreter"
    raw_path = DATA_DIR / "raw" / "overpass_landmarks.json"
    if normalize_only:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    for attempt in range(0 if normalize_only else 3):
        try:
            response = httpx.post(endpoint, data={"data": QUERY}, headers={"User-Agent": USER_AGENT}, timeout=120)
            response.raise_for_status()
            raw = response.json()
            if raw.get("remark") or not raw.get("elements"):
                raise ValueError("Incomplete response")
            break
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                raise
            time.sleep(15*(attempt+1))
    existing_manifest = DATA_DIR / "manifests" / "landmarks.json"
    collected = json.loads(existing_manifest.read_text(encoding="utf-8"))["collected_at"] if normalize_only and existing_manifest.exists() else datetime.now(timezone.utc).isoformat()
    landmarks = []
    for element in raw["elements"]:
        tags = element.get("tags", {})
        coords = element if element["type"] == "node" else element.get("center", {})
        # Exclude incidental businesses named after landmarks from defaults.
        if not all(key in coords for key in ("lat", "lon")) or tags.get("access") in {"no", "private"}:
            continue
        if tags.get("amenity") in {"cafe", "restaurant", "bank"} or tags.get("shop") not in {None, "mall"}:
            continue
        if not (tags.get("historic") == "monument" or tags.get("shop") == "mall" or tags.get("amenity") == "exhibition_centre" or tags.get("leisure") == "park" or tags.get("place") == "quarter" and "2017" in tags.get("name", "")):
            continue
        landmarks.append({"id": f"osm:{element['type']}:{element['id']}", "name": tags["name"],
                          "latitude": coords["lat"], "longitude": coords["lon"], "category": "landmark",
                          "source_url": f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
                          "coordinate_kind": "node" if element["type"] == "node" else "polygon_center",
                          "alternative_names": [v for k,v in tags.items() if k in {"name:ru","name:kk","name:en","alt_name"}],
                          "tags": tags, "collected_at": collected, "source_updated_at": element.get("timestamp")})
    atomic_json(DATA_DIR / "raw" / "overpass_landmarks.json", raw)
    atomic_json(DATA_DIR / "processed" / "landmarks.json", landmarks)
    atomic_json(DATA_DIR / "manifests" / "landmarks.json", {"collected_at": collected, "query": QUERY, "source_url": endpoint,
                "bbox_south_west_north_east": BBOX, "raw_count": len(raw["elements"]), "accepted_count": len(landmarks),
                "checksum": digest(landmarks), "raw_checksum": digest(raw), "license": "ODbL 1.0",
                "usage": "Local origin search only; no invented recommendation category",
                "bbox_verification": [{"name": p["name"], "latitude": p["latitude"], "longitude": p["longitude"], "source_url": p["source_url"]} for p in landmarks]})
    print(json.dumps({"landmarks": len(landmarks), "names": [p["name"] for p in landmarks]}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--normalize-only", action="store_true")
    main(parser.parse_args().normalize_only)
