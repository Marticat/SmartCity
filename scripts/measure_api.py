"""Measure an already running real API using only a public dataset anchor."""
import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output", default="tests/benchmark/api-latency.json")
    args = parser.parse_args()
    data = json.loads((ROOT / "data/processed/pois.json").read_text(encoding="utf-8"))
    anchor = next(p for p in data if p["id"] == "osm:way:1196402246")
    body = {"query":"Не кафе, хочу парк","time_budget_minutes":60,
            "origin":{"latitude":anchor["latitude"],"longitude":anchor["longitude"]}}
    rows = []
    with httpx.Client(base_url=args.url, timeout=60) as client:
        health = client.get("/health").json()
        dataset = client.get("/api/dataset/status").json()
        for i in range(args.runs):
            start = time.perf_counter()
            response = client.post("/api/recommend", json=body)
            elapsed = (time.perf_counter()-start)*1000
            response.raise_for_status()
            result = response.json()
            rows.append({"run":i+1,"wall_ms":round(elapsed,2),"server_ms":result["trace"]["elapsed_ms"],
                "mode":result["mode"],"weather":result["weather"]["status"],
                "poi_ids":[r["poi"]["id"] for r in result["recommendations"]],
                "retrieval":result["trace"]["retrieval_method"]})
    warm = [r["wall_ms"] for r in rows[1:]]
    output = {"measured_at":datetime.now(timezone.utc).isoformat(),"runs":args.runs,"health":health,
              "dataset_checksum":dataset.get("checksum"),"embedding_model":dataset.get("embedding_model"),
              "anchor_public_poi_id":anchor["id"],"first_request_ms":rows[0]["wall_ms"],
              "warm_request_median_ms":round(statistics.median(warm),2) if warm else None,
              "warm_request_max_ms":max(warm) if warm else None,
              "note":"Full HTTP endpoint, warmed server. First request is separate, not process cold start. LLM is included only when mode=rag. Weather may be cached. Local machine, no load test.",
              "results":rows}
    target = ROOT / args.output
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in output.items() if k!="results"},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
