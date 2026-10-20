"""Local semantic + FTS5 search. Every ranked pool has already passed constraints."""
import json
import re
import sqlite3
import threading
from contextlib import closing
from types import SimpleNamespace
from datetime import datetime, timezone
import numpy as np
from .config import DATA_DIR, MODEL_NAME, MODEL_PATH, MODEL_REVISION
from .data import digest
from .schemas.models import DatasetStatus, POI


class Store:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        self.pois = []
        self.by_id = {}
        self.vectors = None
        self.model = None
        self.semantic_error = None
        self.lock = threading.Lock()
        self.manifest = {}
        self.index_manifest = {}
        self.landmarks = []
        self.load()

    def load(self):
        path = self.data_dir / "processed" / "pois.json"
        if not path.exists():
            return
        rows = json.loads(path.read_text(encoding="utf-8"))
        landmark_path = self.data_dir / "processed" / "landmarks.json"
        if landmark_path.exists():
            self.landmarks = [SimpleNamespace(**p) for p in json.loads(landmark_path.read_text(encoding="utf-8"))]
        self.pois = [POI.model_validate(row) for row in rows]
        self.by_id = {p.id: p for p in self.pois}
        self.checksum = digest(rows)
        manifest = self.data_dir / "manifests" / "collection.json"
        if manifest.exists():
            self.manifest = json.loads(manifest.read_text(encoding="utf-8"))
        indexpath = self.data_dir / "manifests" / "index.json"
        if indexpath.exists():
            self.index_manifest = json.loads(indexpath.read_text(encoding="utf-8"))
            metadata = self.index_manifest
            revision_matches = MODEL_REVISION == metadata.get("requested_revision", "main") or MODEL_REVISION == metadata.get("revision")
            if metadata.get("dataset_checksum") == self.checksum and metadata.get("model") == MODEL_NAME and revision_matches and metadata.get("poi_ids") == [p.id for p in self.pois]:
                try:
                    self.vectors = np.load(self.data_dir / "index" / "embeddings.npy", allow_pickle=False)
                    if self.vectors.shape[0] != len(self.pois):
                        self.vectors = None
                except (OSError, ValueError):
                    self.semantic_error = "Индекс embeddings не читается. Запустите scripts.index_pois."
            else:
                self.semantic_error = "Версия индекса не совпадает с данными. Перестройте индекс."

    def load_model(self):
        if self.model is None and self.vectors is not None:
            with self.lock:
                if self.model is None:
                    try:
                        import torch
                        from sentence_transformers import SentenceTransformer
                        torch.set_num_threads(4)
                        # Never download at request time. Preparation owns the model cache.
                        self.model = SentenceTransformer(str(self.data_dir / "models" / "multilingual-e5-small"), local_files_only=True, device="cpu")
                    except Exception:
                        self.vectors = None
                        self.semantic_error = "Локальная semantic-модель недоступна. Доступен текстовый поиск."
        return self.model

    @property
    def semantic_ready(self):
        return self.vectors is not None and self.model is not None

    def status(self):
        collected = self.manifest.get("collected_at")
        stale = False
        if collected:
            stale = (datetime.now(timezone.utc) - datetime.fromisoformat(collected)).days > 30
        return DatasetStatus(ready=bool(self.pois), poi_count=len(self.pois), collected_at=collected,
                             checksum=getattr(self, "checksum", None), semantic_ready=self.semantic_ready,
                             embedding_model=self.index_manifest.get("model"), stale=stale,
                             coverage={**self.manifest.get("area", {}), "quality": self.manifest.get("quality", {})})

    def lexical(self, query, allowed_ids=None):
        tokens = re.findall(r"[^\W_]+", query.lower(), re.UNICODE)[:30]
        if not tokens:
            return []
        match = " OR ".join('"' + token + '"*' for token in tokens)
        dbpath = self.data_dir / "index" / "pois.sqlite"
        if not dbpath.exists():
            return []
        with closing(sqlite3.connect(dbpath)) as connection:
            rows = connection.execute("SELECT poi_id FROM poi_fts WHERE poi_fts MATCH ? ORDER BY bm25(poi_fts) ASC", (match,)).fetchall()
        return [r[0] for r in rows if allowed_ids is None or r[0] in allowed_ids]

    def search(self, query, candidates, limit=24):
        allowed = {p.id for p in candidates}
        if not allowed:
            return []
        lex = self.lexical(query, allowed)
        rankings = [lex]
        model = self.load_model()
        if model is not None:
            with self.lock:
                vector = model.encode(["query: " + query], normalize_embeddings=True, show_progress_bar=False)[0]
            positions = [i for i, p in enumerate(self.pois) if p.id in allowed]
            similarities = self.vectors[positions] @ vector
            semantic = [self.pois[positions[i]].id for i in np.argsort(-similarities)]
            rankings.append(semantic)
        scores = {id: 0.0 for id in allowed}
        for ranking in rankings:
            for rank, id in enumerate(ranking):
                scores[id] += 1.0 / (60 + rank + 1)
        return [(self.by_id[id], score) for id, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:limit]]

    def locations(self, query="", limit=8):
        # Small independent landmark snapshot can be refreshed without invalidating POI embeddings.
        landmark_path = self.data_dir / "processed" / "landmarks.json"
        if landmark_path.exists():
            self.landmarks = [SimpleNamespace(**p) for p in json.loads(landmark_path.read_text(encoding="utf-8"))]
        if query.strip():
            q = query.casefold()
            landmark_matches = [p for p in self.landmarks if q in " ".join([p.name, *p.alternative_names]).casefold()]
            # A location picker is a name search, not a recommendation search.
            # Exact/phrase name matches must precede incidental description words.
            def name_rank(place):
                aliases = [getattr(place, k, None) for k in ("name", "name_ru", "name_kk", "name_en")]
                aliases += getattr(place, "alternative_names", [])
                normalized = [re.sub(r"\W+", " ", a.casefold()).strip() for a in aliases if a]
                needle = re.sub(r"\W+", " ", q).strip()
                return 0 if needle in normalized else 1 if any(needle in a for a in normalized) else 2
            name_matches = [p for p in self.pois if name_rank(p) < 2]
            ids = self.lexical(query)
            if not ids:
                q = query.casefold()
                ids = [p.id for p in self.pois if q in " ".join(filter(None, [p.name, p.name_ru, p.name_en, p.name_kk, *p.alternative_names])).casefold()]
            merged = {p.id: p for p in [*landmark_matches, *name_matches, *[self.by_id[id] for id in ids if id in self.by_id]]}
            return sorted(merged.values(), key=name_rank)[:limit]
        # Landmarks selected by actual recorded name, no fabricated coordinates.
        names = ("нұр әлем", "nur alem", "байтерек", "бәйтерек", "ботан", "центральный парк")
        landmarks = [p for term in names for p in self.pois if term in p.name.casefold()]
        unique = list({p.id: p for p in landmarks}.values())
        combined = self.landmarks + unique or self.pois
        distinct = {}
        for place in combined:
            distinct.setdefault(place.id, place)
        return list(distinct.values())[:limit]
