"""Server configuration. Public data only; secrets never appear in status output."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
MODEL_REVISION = os.getenv("EMBEDDING_REVISION", "main")
MODEL_PATH = DATA_DIR / "models" / "multilingual-e5-small"
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
USER_AGENT = "QADAM-Astana/1.0 (educational POI research; batch collection)"
# Deliberate demo rectangle, not an assertion of administrative boundaries.
# Bounds contain the OSM city centre and the verified EXPO area.
BBOX = (51.02, 71.30, 51.23, 71.55)
CATEGORY_LABELS = {"cafe": "Кафе", "museum": "Музей", "park": "Парк", "playground": "Детская площадка", "gallery": "Галерея", "viewpoint": "Смотровая площадка", "attraction": "Достопримечательность", "artwork": "Публичное искусство", "theatre": "Театр"}
VISIT_MINUTES = {"cafe": (15, 30), "museum": (30, 60), "park": (15, 35), "playground": (15, 30), "gallery": (20, 40), "viewpoint": (10, 20), "attraction": (10, 25), "artwork": (5, 15), "theatre": (20, 40)}
