"""Build SQLite FTS + pinned, normalized multilingual-e5 embeddings offline."""
import argparse
import json
import sqlite3
import time
from contextlib import closing
import numpy as np
from huggingface_hub import HfApi
from sentence_transformers import SentenceTransformer
import torch
from backend.app.config import DATA_DIR, MODEL_NAME, MODEL_PATH, MODEL_REVISION
from backend.app.data import atomic_json, digest, document
from backend.app.schemas.models import POI


def main(lexical_only=False):
    start = time.perf_counter()
    rows = json.loads((DATA_DIR / "processed" / "pois.json").read_text(encoding="utf-8"))
    pois = [POI.model_validate(row) for row in rows]
    directory = DATA_DIR / "index"
    directory.mkdir(parents=True, exist_ok=True)
    dbpath = directory / "pois.sqlite.tmp"
    if dbpath.exists():
        dbpath.unlink()
    with closing(sqlite3.connect(dbpath)) as connection:
        with connection:
            connection.execute("CREATE VIRTUAL TABLE poi_fts USING fts5(poi_id UNINDEXED, document, tokenize='unicode61')")
            connection.executemany("INSERT INTO poi_fts(poi_id,document) VALUES (?,?)", [(p.id, document(p)) for p in pois])
    dbpath.replace(directory / "pois.sqlite")
    if lexical_only:
        print("FTS5 index ready; semantic index not requested")
        return
    torch.set_num_threads(4)
    old_path = DATA_DIR / "manifests" / "index.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
    if MODEL_PATH.exists() and old.get("model") == MODEL_NAME and MODEL_REVISION in {old.get("requested_revision", "main"), old.get("revision")}:
        revision = old["revision"]
        model = SentenceTransformer(str(MODEL_PATH), device="cpu", local_files_only=True)
    else:
        revision = HfApi().model_info(MODEL_NAME, revision=MODEL_REVISION).sha
        model = SentenceTransformer(MODEL_NAME, revision=revision, device="cpu")
        model.save(str(MODEL_PATH))
    embeddings = model.encode(["passage: " + document(p) for p in pois], batch_size=32, normalize_embeddings=True, show_progress_bar=True)
    temporary = directory / "embeddings.tmp.npy"
    np.save(temporary, np.asarray(embeddings, dtype=np.float32))
    temporary.replace(directory / "embeddings.npy")
    atomic_json(old_path, {"model": MODEL_NAME, "requested_revision": MODEL_REVISION, "revision": revision, "dataset_checksum": digest(rows), "poi_ids": [p.id for p in pois], "dimensions": int(embeddings.shape[1]), "normalized": True, "query_prefix": "query: ", "document_prefix": "passage: ", "elapsed_seconds": round(time.perf_counter()-start, 3)})
    print(json.dumps({"pois": len(pois), "dimensions": int(embeddings.shape[1]), "revision": revision, "seconds": round(time.perf_counter()-start, 2)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexical-only", action="store_true")
    main(parser.parse_args().lexical_only)
