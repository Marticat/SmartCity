"""Run real conversational inputs against the real API; produce auditable checks.

No production parser/filter is imported. Never auto-score subjective relevance.
"""
import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def air_distance(origin, poi):
    lat1, lat2 = map(math.radians, (origin["latitude"], poi["latitude"]))
    dlat = lat2-lat1
    dlon = math.radians(poi["longitude"]-origin["longitude"])
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2)))


def objective_checks(case, body, origin, public_ids):
    failures = []
    recs = body.get("recommendations", [])
    if len(recs) > 3:
        failures.append("more_than_three")
    if case.get("expect_empty") and recs:
        failures.append("expected_empty")
    if case.get("expect_some") and not recs:
        failures.append("expected_some")
    if case.get("expect_clarification") and not body.get("clarifying_question"):
        failures.append("missing_clarification")
    if case.get("required_warning_term") and case["required_warning_term"] not in " ".join(body.get("warnings",[])).lower():
        failures.append("missing_context_warning")
    for rec in recs:
        poi = rec["poi"]
        ident = poi["id"]
        if ident not in public_ids:
            failures.append(ident + ":unknown_poi")
        elif isinstance(public_ids, dict):
            canonical = public_ids[ident]
            if any(poi.get(field) != canonical.get(field) for field in
                   ("name","category","latitude","longitude","source_url","description","attributes")):
                failures.append(ident + ":source_fields_changed")
        if case.get("allowed_categories") and poi["category"] not in case["allowed_categories"]:
            failures.append(ident + ":wrong_category")
        if poi["category"] in case.get("forbidden_categories", []):
            failures.append(ident + ":forbidden_category")
        for attribute in case.get("required_attributes", []):
            if poi.get("attributes", {}).get(attribute) is not True:
                failures.append(ident + ":unconfirmed_" + attribute)
        for attribute, term in case.get("unknown_disclosures", {}).items():
            if poi.get("attributes", {}).get(attribute) is not True:
                caveats = " ".join(rec.get("caveats", [])).lower()
                if term not in caveats or "не подтвержд" not in caveats:
                    failures.append(ident + ":missing_unknown_disclosure_" + attribute)
        if not poi["source_url"].startswith(("https://www.openstreetmap.org/", "https://")):
            failures.append(ident + ":unsafe_source")
        if any(field not in poi.get("field_provenance", {}) for field in rec["evidence_field_ids"]):
            failures.append(ident + ":unknown_evidence")
        if rec.get("opening_status") == "closed":
            failures.append(ident + ":closed")
        if rec["distance_method"] == "straight_line":
            if rec.get("walking_minutes") is not None or rec.get("total_minutes") is not None:
                failures.append(ident + ":unverified_travel_time")
            if abs(rec["distance_m"] - air_distance(origin, poi)) > 3:
                failures.append(ident + ":incorrect_air_distance")
            if not any("не провер" in c.lower() or "не гарант" in c.lower() for c in rec.get("caveats", [])):
                failures.append(ident + ":missing_route_caveat")
        if rec.get("total_minutes") is not None and rec["total_minutes"] > case["max_effective_minutes"]:
            failures.append(ident + ":over_budget")
        if not poi.get("opening_hours_raw") and rec.get("opening_status") != "unknown":
            failures.append(ident + ":invented_opening")
    trace = " ".join(body.get("trace", {}).get("applied_constraints", []))
    match = re.search(r"Время:\s*(\d+)\s*мин", trace)
    if match and int(match.group(1)) > case["max_effective_minutes"]:
        failures.append("silently_expanded_time")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="tests/benchmark/conversation-results.json")
    args = parser.parse_args()
    spec_bytes = (ROOT / "tests/benchmark/conversations.json").read_bytes()
    spec = json.loads(spec_bytes)
    pois = json.loads((ROOT / "data/processed/pois.json").read_text(encoding="utf-8"))
    landmarks_path = ROOT / "data/processed/landmarks.json"
    landmarks = json.loads(landmarks_path.read_text(encoding="utf-8")) if landmarks_path.exists() else []
    anchors = {p["id"]: p for p in [*pois, *landmarks]}
    public_ids = {p["id"]:p for p in pois}
    rows = []
    with httpx.Client(base_url=args.url, timeout=90) as client:
        status = client.get("/api/dataset/status").json()
        for case in spec["cases"]:
            anchor = case.get("origin_public_city") or anchors[case["anchor_id"]]
            origin = {k: anchor[k] for k in ("latitude", "longitude")}
            request = {"query":case["query"],"origin":origin,"preset":case["preset"],
                       "time_budget_minutes":case["minutes"],"return_to_start":case.get("return_to_start",False)}
            if case.get("visit_datetime"):
                request["visit_datetime"]=case["visit_datetime"]
            started = time.perf_counter()
            response = client.post("/api/recommend", json=request)
            if response.status_code == 429:
                raise SystemExit("API rate limit reached. Wait one minute, then rerun; no partial evaluation written.")
            response.raise_for_status()
            body = response.json()
            rows.append({"id":case["id"],"query":case["query"],"anchor_id":case.get("anchor_id","public:almaty"),
                "objective_failures":objective_checks(case,body,origin,public_ids),
                "wall_ms":round((time.perf_counter()-started)*1000,2),"mode":body["mode"],
                "visit_datetime":case.get("visit_datetime"),
                "summary":body["summary"],"clarifying_question":body["clarifying_question"],
                "warnings":body["warnings"],"trace":body["trace"],"weather":body["weather"],
                "recommendations":[{"poi_id":r["poi"]["id"],"name":r["poi"]["name"],"category":r["poi"]["category"],
                    "description":r["poi"]["description"],"attributes":r["poi"]["attributes"],
                    "source_url":r["poi"]["source_url"],"why_suitable":r["why_suitable"],
                    "suggested_activity":r["suggested_activity"],"activity_origin":r["activity_origin"],
                    "distance_m":r["distance_m"],"distance_method":r["distance_method"],
                    "visit_minutes_min":r["visit_minutes_min"],"visit_minutes_max":r["visit_minutes_max"],
                    "total_minutes":r["total_minutes"],"caveats":r["caveats"]} for r in body["recommendations"]],
                "human_review_question":case["human_question"],"human_score":None})
    result = {"measured_at":datetime.now(timezone.utc).isoformat(),"dataset_checksum":status["checksum"],
        "cases_sha256":hashlib.sha256(spec_bytes).hexdigest(),
        "semantic_ready":status["semantic_ready"],"cases":len(rows),
        "objective_passed":sum(not r["objective_failures"] for r in rows),
        "human_relevance":"not_scored; requires human reviewer, not an LLM self-rating",
        "median_wall_ms":round(statistics.median(r["wall_ms"] for r in rows),2),
        "method":"Real local API and real dataset; no POI mocks. Live weather/provider availability recorded. No quality claim from objective pass count.",
        "results":rows}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    sheet = output.with_name("human-review.csv")
    # Separate writable human form; protect prior reviewer work.
    if not sheet.exists():
        with sheet.open("w",encoding="utf-8-sig",newline="") as stream:
            writer=csv.writer(stream)
            writer.writerow(["case_id","question","relevance_0_to_2","evidence_0_to_2","actionability_0_to_2","reviewer","notes"])
            for row in rows:
                writer.writerow([row["id"],row["human_review_question"],"","","","",""])
    print(json.dumps({"cases":len(rows),"objective_passed":result["objective_passed"],
        "failed":[{"id":r["id"],"failures":r["objective_failures"]} for r in rows if r["objective_failures"]],
        "human_relevance":"not_scored","output":str(output)},ensure_ascii=False,indent=2))
    return 0 if result["objective_passed"]==len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
