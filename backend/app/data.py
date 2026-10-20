"""OSM normalization, provenance, atomic local snapshots and FTS documents."""
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from .config import CATEGORY_LABELS
from .schemas.models import POI


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def safe_url(value):
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"https", "http"} and parsed.netloc and not parsed.username else None


def category_of(tags):
    if tags.get("amenity") == "cafe":
        return "cafe"
    if tags.get("amenity") == "theatre":
        return "theatre"
    if tags.get("leisure") in {"park", "playground"}:
        return tags["leisure"]
    if tags.get("tourism") in {"museum", "gallery", "viewpoint", "attraction", "artwork"}:
        return tags["tourism"]
    return None


def tri(value):
    return True if value in {"yes", "wlan", "free"} else False if value in {"no", "none"} else None


def normalize_elements(elements, collected_at):
    pois, rejected, seen = [], Counter(), set()
    for el in elements:
        tags = el.get("tags", {})
        identity = f"osm:{el['type']}:{el['id']}"
        if identity in seen:
            rejected["duplicate_source_id"] += 1
            continue
        seen.add(identity)
        if tags.get("access") in {"private", "no", "customers_only"} or tags.get("indoor") == "room":
            rejected["restricted_access"] += 1
            continue
        if any(k.startswith(("disused:", "abandoned:", "demolished:", "construction:")) for k in tags) or any(tags.get(k) == "yes" for k in ("disused", "abandoned", "construction")) or tags.get("building") in {"construction", "abandoned", "disused"}:
            rejected["inactive"] += 1
            continue
        category = category_of(tags)
        if not category:
            rejected["unsupported_category"] += 1
            continue
        coords = el if el["type"] == "node" else el.get("center", {})
        if not all(k in coords for k in ("lat", "lon")):
            rejected["missing_coordinates"] += 1
            continue
        names = [tags.get(k) for k in ("name", "name:ru", "name:kk", "name:en")]
        name = next((n for n in names if n), None)
        # Unnamed playgrounds are legitimate useful POI; transparent generic label.
        if not name:
            if category not in {"playground", "park"}:
                rejected["missing_name"] += 1
                continue
            name = CATEGORY_LABELS[category] + " (без названия в OSM)"
        url = f"https://www.openstreetmap.org/{el['type']}/{el['id']}"
        address = ", ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")])) or None
        internet_types = {part.strip() for part in tags.get("internet_access", "").split(";")}
        # OSM internet_access=yes confirms some internet service, not its mode.
        wifi = True if "wlan" in internet_types else False if internet_types == {"no"} else None
        if tags.get("wifi") in {"yes", "no"}:
            wifi = tri(tags["wifi"])
        attrs = {"indoor": tri(tags.get("indoor")), "wifi": wifi, "sockets": tri(tags.get("socket")), "wheelchair": tri(tags.get("wheelchair")), "free": False if tags.get("fee") == "yes" else True if tags.get("fee") == "no" else None}
        # Categories never imply confirmed indoor access.
        if tags.get("internet_access:wlan") in {"yes", "no"}:
            attrs["wifi"] = tri(tags["internet_access:wlan"])
        evidence = {key: {"source_url": url, "collected_at": collected_at, "source_updated_at": el.get("timestamp")} for key in ("name", "category", "latitude", "longitude")}
        for k, v in attrs.items():
            if v is not None:
                evidence[f"attributes.{k}"] = {"source_url": url, "collected_at": collected_at, "value": v}
        for key, value in (("address", address), ("opening_hours_raw", tags.get("opening_hours"))):
            if value:
                evidence[key] = {"source_url": url, "collected_at": collected_at, "value": value}
        description = CATEGORY_LABELS[category] + (f"; в данных указан адрес: {address}." if address else ". Адрес в источнике не указан.")
        record = dict(id=identity, source_id=f"{el['type']}/{el['id']}", source_url=url, name=name,
                      name_ru=tags.get("name:ru"), name_kk=tags.get("name:kk"), name_en=tags.get("name:en"),
                      alternative_names=[n.strip() for n in tags.get("alt_name", "").split(";") if n.strip()],
                      latitude=coords["lat"], longitude=coords["lon"], coordinate_kind="node" if el["type"] == "node" else "polygon_center",
                      category=category, tags=tags, address=address, description=description,
                      opening_hours_raw=tags.get("opening_hours"), website=safe_url(tags.get("website") or tags.get("contact:website")),
                      public_contact=tags.get("contact:phone") or tags.get("phone"), attributes=attrs,
                      field_provenance=evidence, source_updated_at=el.get("timestamp"), collected_at=collected_at)
        record["content_hash"] = digest({k: v for k, v in record.items() if k not in {"collected_at", "field_provenance"}})
        poi = POI(**record)
        # Only merge named near-identical objects of the same category within 20m.
        keyname = re.sub(r"\W+", "", name.lower())
        duplicate = next((p for p in pois if p.category == category and "без названия" not in name and re.sub(r"\W+", "", p.name.lower()) == keyname and math.hypot((p.latitude-poi.latitude)*111000, (p.longitude-poi.longitude)*70000) < 20), None)
        if duplicate:
            rejected["spatial_name_duplicate"] += 1
            continue
        pois.append(poi)
    return pois, dict(rejected)


def document(poi):
    aliases = " ".join(filter(None, [poi.name, poi.name_ru, poi.name_kk, poi.name_en, *poi.alternative_names]))
    known = " ".join(f"{k} {v}" for k, v in poi.attributes.items() if v is not None)
    return f"{aliases}. {CATEGORY_LABELS.get(poi.category, poi.category)} {poi.category}. {poi.description} {known}"
