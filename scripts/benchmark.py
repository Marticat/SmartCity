"""Frozen real-POI retrieval evaluation; no provider calls and no fabricated labels."""
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from backend.app.constraints import filter_candidates, parse_intent
from backend.app.retrieval import Store
from backend.app.schemas.models import RecommendRequest
from backend.app.data import digest

ROOT = Path(__file__).resolve().parents[1]


def main():
    labels = json.loads((ROOT / "tests/benchmark/frozen.json").read_text(encoding="utf-8"))
    start = time.perf_counter()
    store = Store()
    store.load_model()
    cold_ms = (time.perf_counter() - start) * 1000
    if store.checksum != labels["dataset_checksum"]:
        raise SystemExit("Frozen dataset checksum mismatch; do not silently relabel evaluation.")
    rows = []
    for case in labels["cases"]:
        anchor = store.by_id[case["anchor_id"]]
        request = RecommendRequest(
            query=case["query"], origin={"latitude": anchor.latitude, "longitude": anchor.longitude},
            time_budget_minutes=case["minutes"], constraints=case.get("constraints", {}),
            visit_datetime=labels["visit_datetime"])
        started = time.perf_counter()
        intent = parse_intent(request)
        candidates = filter_candidates(store.pois, request, intent, request.visit_datetime)
        retrieved = store.search(request.query, [p for p, _, _ in candidates], 3)
        ms = (time.perf_counter() - started) * 1000
        ids = [p.id for p, _ in retrieved]
        relevant = set(case["relevant_ids"])
        violations = []
        for p, _ in retrieved:
            if p.category in case.get("forbidden_categories", []):
                violations.append(p.id + ":forbidden_category")
            for attribute, constraint in [("sockets","sockets_required"),("wifi","wifi_required"),("indoor","indoor_only")]:
                if case.get("constraints", {}).get(constraint) and p.attributes.get(attribute) is not True:
                    violations.append(p.id + ":unknown_" + attribute)
        rows.append({"id":case["id"],"returned_ids":ids,"relevant_ids":case["relevant_ids"],"hit":bool(set(ids)&relevant),
                     "precision_at_3":len(set(ids)&relevant)/3,"constraint_violations":violations,
                     "expected_empty":case.get("expect_empty", False),"empty_correct":not ids if case.get("expect_empty") else None,
                     "retrieval_ms":round(ms,2)})
    named = rows[:12]
    timings = [r["retrieval_ms"] for r in rows]
    result = {
        "measured_at":datetime.now(timezone.utc).isoformat(),"platform":platform.platform(),"python":platform.python_version(),
        "dataset_checksum":store.checksum,"labels_checksum":digest(labels),"model":store.index_manifest.get("model"),
        "model_revision":store.index_manifest.get("revision"),"semantic_ready":store.semantic_ready,
        "mode":"hybrid_retrieval" if store.semantic_ready else "lexical_only",
        "cases":len(rows),"named_query_hit_at_3":sum(r["hit"] for r in named)/len(named),
        "named_query_precision_at_3":statistics.mean(r["precision_at_3"] for r in named),
        "precision_note":"Each named query has one relevant POI; fixed-denominator precision@3 is capped at 1/3. hit@3 is the useful named-location measure.",
        "constraint_violation_rate":sum(bool(r["constraint_violations"]) for r in rows)/len(rows),
        "cold_store_and_model_load_ms":round(cold_ms,2),
        "warm_retrieval_median_ms":round(statistics.median(timings),2),"warm_retrieval_max_ms":max(timings),
        "provider_calls":0,"results":rows,
    }
    (ROOT / "tests/benchmark/results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
