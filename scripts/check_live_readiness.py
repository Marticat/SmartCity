"""Bounded real provider smoke checks; only redacted receipts are written.

No key => skipped. Existing app keys are read server-side from environment/.env.
This command never accepts keys as CLI arguments or dumps provider responses.
"""
import argparse
import asyncio
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.app.config import LLM_MODEL
from backend.app.schemas.models import Origin, RecommendRequest, Weather

ROOT = Path(__file__).resolve().parents[1]


def safe_model_name(value):
    return value if re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", value or "") else "configured-model"


def missing(name):
    return {"status":"skipped","reason":"missing_server_variable","required_variable":name}


async def check_gemini():
    if not os.getenv("GEMINI_API_KEY"):
        return missing("GEMINI_API_KEY")
    from backend.app import main as server
    await asyncio.to_thread(server.store.load_model)
    if not server.store.semantic_ready:
        return {"status":"skipped","reason":"semantic_index_not_ready","next_command":"python -m scripts.index_pois"}
    cafes = [p for p in server.store.pois if p.category == "cafe" and p.coordinate_kind == "node"]
    if not cafes:
        return {"status":"skipped","reason":"no_real_cafe_anchor"}
    anchor = next((p for p in cafes if p.id == "osm:node:9047331879"), cafes[0])

    class NoWeather:
        async def get(self, *args):
            return Weather()
    class NoRouting:
        async def route(self, *args):
            return None
    # Process-local isolation bounds billing and separates failures by provider.
    # Real POIs, intent, retrieval, generator and grounding remain unchanged.
    previous_weather, previous_routing = server.weather_service, server.routing_service
    server.weather_service, server.routing_service = NoWeather(), NoRouting()
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(server.recommend_impl(RecommendRequest(
            query="Кофе рядом на 60 минут", preset="coffee", time_budget_minutes=60,
            origin=Origin(latitude=anchor.latitude, longitude=anchor.longitude))), timeout=60)
        passed = result.mode == "rag" and bool(result.recommendations) and all(
            r.poi.id in server.store.by_id and r.activity_origin == "ai" for r in result.recommendations)
        return {"status":"passed" if passed else "failed",
                "reason":"real_grounded_rag_response" if passed else "provider_or_grounding_failed",
                "model":safe_model_name(LLM_MODEL),"mode":result.mode,
                "dataset_checksum":result.dataset.checksum,"public_anchor_id":anchor.id,
                "recommendation_ids":[r.poi.id for r in result.recommendations],
                "elapsed_ms":round((time.perf_counter()-started)*1000,2),
                "auxiliary_services":"weather/routing disabled for this isolated provider check",
                "generated_text_stored":False}
    finally:
        server.weather_service, server.routing_service = previous_weather, previous_routing


async def check_ors():
    if not os.getenv("ORS_API_KEY"):
        return missing("ORS_API_KEY")
    from backend.app.retrieval import Store
    from backend.app.services import RoutingService
    store = Store()
    nodes = [p for p in store.pois if p.coordinate_kind == "node"]
    if len(nodes) < 2:
        return {"status":"skipped","reason":"insufficient_real_node_anchors"}
    anchor = next((p for p in nodes if p.id == "osm:node:9047331879"), nodes[0])
    # Public POI nodes only. Centroids and personal positions are never used.
    def approximate_distance(p):
        return math.hypot((p.latitude-anchor.latitude)*111000,
                          (p.longitude-anchor.longitude)*111000*math.cos(math.radians(anchor.latitude)))
    candidates = [p for p in nodes if p.id != anchor.id and 100 < approximate_distance(p) < 1500]
    if not candidates:
        return {"status":"skipped","reason":"no_nearby_public_node_pair"}
    target = min(candidates, key=approximate_distance)
    started = time.perf_counter()
    result = await asyncio.wait_for(RoutingService().route(
        Origin(latitude=anchor.latitude,longitude=anchor.longitude),target,return_to_start=True),timeout=20)
    if result is None:
        return {"status":"failed","reason":"provider_returned_no_verified_route",
                "public_anchor_ids":[anchor.id,target.id],
                "elapsed_ms":round((time.perf_counter()-started)*1000,2)}
    geometry = result["geometry"].get("coordinates",[])
    def anchor_gap(coord):
        return math.hypot((coord[1]-anchor.latitude)*111000,
                          (coord[0]-anchor.longitude)*111000*math.cos(math.radians(anchor.latitude)))
    passed = (result["minutes"] > 0 and result["outbound_minutes"] > 0 and
              result["minutes"] > result["outbound_minutes"] and
              result["total_distance_m"] > result["distance_m"] > 0 and
              result["geometry"]["type"] == "LineString" and
              len(geometry) >= 3 and anchor_gap(geometry[0]) < 500 and anchor_gap(geometry[-1]) < 500)
    return {"status":"passed" if passed else "failed",
            "reason":"real_walking_roundtrip" if passed else "invalid_route_response",
            "provider":"openrouteservice","profile":"foot-walking","return_to_start":True,
            "public_anchor_ids":[anchor.id,target.id],"outbound_distance_m":result["distance_m"],
            "total_distance_m":result["total_distance_m"],"total_walking_minutes":result["minutes"],
            "outbound_minutes":result["outbound_minutes"],"geometry_points":len(geometry),
            "elapsed_ms":round((time.perf_counter()-started)*1000,2)}


async def run(providers):
    results = {}
    for name, function in (("gemini",check_gemini),("ors",check_ors)):
        if providers not in {"all",name}:
            continue
        try:
            results[name] = await function()
        except Exception as error:
            # Never serialize str(error), HTTP headers, body, URLs, keys or prompts.
            results[name] = {"status":"failed","reason":"check_exception","exception_type":type(error).__name__}
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers",choices=["all","gemini","ors"],default="all")
    parser.add_argument("--output",default="docs/live-readiness.json")
    parser.add_argument("--require-all",action="store_true",help="Exit nonzero if any selected check failed or was skipped")
    args=parser.parse_args()
    checks=asyncio.run(run(args.providers))
    receipt={"checked_at":datetime.now(timezone.utc).isoformat(),
             "all_selected_passed":bool(checks) and all(c["status"]=="passed" for c in checks.values()),
             "credentials_stored":False,"raw_provider_responses_stored":False,
             "checks":checks}
    target=ROOT/args.output
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    if args.require_all and not receipt["all_selected_passed"]:
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
