"""QADAM single-process API and optional built frontend serving."""
import asyncio
import os
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .config import CATEGORY_LABELS, ROOT, VISIT_MINUTES
from .constraints import filter_candidates, opening_status, parse_intent, supported
from .generation import ACTIVITIES, GeminiGenerator
from .retrieval import Store
from .schemas.models import RecommendRequest, RecommendResponse, Recommendation, Trace, Weather
from .services import RoutingService, WeatherService

store = Store()
weather_service = WeatherService()
routing_service = RoutingService()
generator = GeminiGenerator()
slots = asyncio.Semaphore(3)
rate_windows = defaultdict(deque)


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(store.load_model)
    yield


app = FastAPI(title="QADAM", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.middleware("http")
async def limits(request: Request, call_next):
    if request.url.path == "/api/recommend":
        content_length = request.headers.get("content-length")
        if content_length and (not content_length.isdigit() or int(content_length) > 16384):
            return JSONResponse(status_code=413, content={"detail": "Запрос слишком большой"})
        # In-memory rate counter only; no persistent IP/location/history log.
        key = request.client.host if request.client else "local"
        now = time.monotonic()
        window = rate_windows[key]
        while window and now-window[0] > 60:
            window.popleft()
        if len(window) >= 30:
            return JSONResponse(status_code=429, content={"detail": "Слишком много запросов. Повторите через минуту."})
        window.append(now)
        if len(rate_windows) > 10000:
            rate_windows.clear()
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "dataset_ready": bool(store.pois), "semantic_ready": store.semantic_ready, "llm_configured": generator.configured}


@app.get("/api/dataset/status")
def dataset_status():
    return store.status()


@app.get("/api/locations/search")
def locations(q: str = Query(default="", max_length=200), limit: int = Query(default=8, ge=1, le=20)):
    return {"locations": [{"id": p.id, "name": p.name, "latitude": p.latitude, "longitude": p.longitude, "category": p.category} for p in store.locations(q, limit)]}


@app.get("/api/pois/{poi_id}")
def poi(poi_id: str):
    if poi_id not in store.by_id:
        raise HTTPException(404, "Место не найдено в локальном наборе данных")
    return store.by_id[poi_id]


async def recommend_impl(request: RecommendRequest):
    start = time.perf_counter()
    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    intent = parse_intent(request)
    dataset = store.status()
    response = RecommendResponse(request_id=request_id, mode="search_only" if dataset.semantic_ready else "lexical_only",
        summary="", dataset=dataset, warnings=list(intent.conflicts),
        trace=Trace(candidate_count=len(store.pois), sources=["OpenStreetMap"], retrieval_method="semantic + FTS5 / RRF" if dataset.semantic_ready else "FTS5"))
    def done():
        response.trace.elapsed_ms = round((time.perf_counter()-start)*1000, 2)
        response.dataset = store.status()
        return response
    if not dataset.ready:
        response.summary = "Локальный набор мест ещё не подготовлен."
        response.warnings.append("Администратору: выполните scripts.collect_pois и scripts.index_pois.")
        return done()
    if not request.origin:
        response.summary = "Выберите отправную точку на карте или найдите ориентир."
        response.clarifying_question = "Откуда начнём прогулку?"
        return done()
    if not supported(request.origin):
        response.summary = "Эта точка за пределами демо-зоны Астаны."
        response.clarifying_question = "Выберите точку в центре Астаны или районе EXPO на карте."
        return done()
    if intent.clarification:
        response.summary = "Нужно уточнить условия прогулки."
        response.clarifying_question = intent.clarification
        return done()
    if dataset.stale:
        response.warnings.append("Набор данных старше 30 дней; сведения стоит проверить перед визитом.")
    if not dataset.semantic_ready:
        response.warnings.append(store.semantic_error or "Семантический индекс не готов: работает ограниченный текстовый поиск.")
    response.trace.applied_constraints = [
        f"Время: {intent.time_budget_minutes} мин",
        "Пешком; географический фильтр до ранжирования",
        *([f"Категории: {', '.join(intent.desired_categories)}"] if intent.desired_categories else []),
        *([f"Исключены: {', '.join(intent.excluded_categories)}"] if intent.excluded_categories else []),
        *[key for key, value in intent.hard_constraints.model_dump().items() if value],
        *[f"Без свойства: {key}" for key in intent.excluded_attributes],
        *(["Учтено возвращение"] if intent.return_to_start else []),
    ]
    filtered = filter_candidates(store.pois, request, intent, now)
    response.trace.filtered_count = len(filtered)
    if not filtered:
        response.summary = "Не нашли мест с подтверждением всех условий."
        response.warnings.append("Попробуйте увеличить время или снять одно обязательное условие. Неизвестные свойства не считаются выполненными.")
        return done()
    response.weather = await weather_service.get(request.origin, intent.visit_datetime)
    if response.weather.status == "unavailable":
        response.warnings.append("Прогноз погоды недоступен; погодные условия не подтверждены.")
    severe = response.weather.status == "available" and ((response.weather.wind_kmh or 0) >= 35 or (response.weather.temperature_c is not None and response.weather.temperature_c <= -10))
    prefer_inside = request.less_outdoors or severe
    if severe:
        response.warnings.append("По прогнозу ожидается сильный ветер или мороз. Поднимаем подтверждённые варианты в помещении; это продуктовый порог.")
    search_query = request.query or {"coffee": "кафе кофе", "family": "парк детская площадка музей", "indoor": "музей галерея кафе", "walk": "парк достопримечательность прогулка"}[request.preset]
    ranked = await asyncio.to_thread(store.search, search_query, [p for p, _, _ in filtered], 24)
    info = {p.id: (distance, status) for p, distance, status in filtered}
    # RRF is combined with small, explicit deterministic proximity/context bonuses.
    generic_query = not request.query.strip() or request.query.strip().casefold() in {"кофе", "кафе", "coffee", "cafe", "парк", "park", "прогулка", "walk", "музей", "museum", "с ребёнком"}
    proximity_weight = 0.04 if generic_query else 0.012
    ranked.sort(key=lambda item: -(item[1] + proximity_weight/(1+info[item[0].id][0]/500) + (0.08 if prefer_inside and item[0].attributes.get("indoor") is True else 0)
        + (0.02 if "prefer_walk" in intent.soft_preferences and not prefer_inside and item[0].category in {"park", "viewpoint", "attraction", "artwork"} else 0)
        + sum(0.005 for attr in ("wifi", "sockets") if f"prefer_{attr}" in intent.soft_preferences and item[0].attributes.get(attr) is True)))
    route_deadline = time.monotonic() + 20
    for place, score in ranked[:8]:
        distance, status = info[place.id]
        visit_min, visit_max = VISIT_MINUTES.get(place.category, (15, 30))
        caveats = []
        walk_minutes = total = None
        method = "straight_line"
        remaining = route_deadline-time.monotonic()
        try:
            route = await asyncio.wait_for(routing_service.route(request.origin, place, intent.return_to_start), timeout=max(0.01, remaining)) if remaining > 0 else None
        except asyncio.TimeoutError:
            route = None
        if route:
            walk_minutes = round(route["minutes"], 1)
            total = round(route["minutes"] + visit_min + 5, 1)
            if total > intent.time_budget_minutes:
                continue
            arrival = (intent.visit_datetime or now) + timedelta(minutes=route["outbound_minutes"])
            status = opening_status(place.opening_hours_raw, arrival, place.source_updated_at, visit_min)
            if status == "closed" or (intent.hard_constraints.open_now and status != "open"):
                continue
            method, distance = "walking", route["distance_m"]
        else:
            caveats.append("Расстояние по прямой. Путь и время перехода не проверены; уложиться в бюджет не гарантируем.")
        if status == "unknown":
            caveats.append("Часы работы на время визита не подтверждены.")
        else:
            caveats.append("Статус рассчитан по расписанию OSM; фактическую работу уточните перед визитом.")
        if place.coordinate_kind == "polygon_center":
            caveats.append("На карте центр объекта, а не проверенный вход.")
        if place.attributes.get("wheelchair") is True:
            caveats.append("Тег доступности относится к объекту; безбарьерность всего пути не проверена.")
        if place.category == "cafe":
            missing = [label for key, label in (("wifi", "Wi-Fi"), ("sockets", "розетки")) if place.attributes.get(key) is None]
            if missing:
                caveats.append("Нет подтверждённых данных: " + ", ".join(missing) + ".")
        if prefer_inside and place.attributes.get("indoor") is not True:
            caveats.append("Нахождение в помещении не подтверждено.")
        evidence = ["category"]
        category_label = CATEGORY_LABELS.get(place.category, place.category)
        reasons = [
            f"«{category_label}» соответствует выбранному интересу." if place.category in intent.desired_categories
            else f"Вариант для остановки рядом: {category_label.lower()}.",
            f"От старта {round(distance)} м {'по пешеходной сети' if method == 'walking' else 'по прямой'}; на посещение рекомендуем {visit_min}–{visit_max} мин."
        ]
        for key, needed in (("indoor", intent.hard_constraints.indoor_only), ("wifi", intent.hard_constraints.wifi_required), ("sockets", intent.hard_constraints.sockets_required), ("wheelchair", intent.hard_constraints.wheelchair_required), ("free", intent.hard_constraints.free_only)):
            if needed and place.attributes.get(key) is True:
                evidence.append("attributes." + key)
                reasons.append({"indoor": "Есть тег помещения.", "wifi": "Есть подтверждение Wi-Fi.", "sockets": "Есть подтверждение розетки.", "wheelchair": "Есть тег доступности объекта.", "free": "В источнике указан бесплатный доступ."}[key])
        rec = Recommendation(poi=place, why_suitable=" ".join(reasons), evidence_field_ids=evidence,
            suggested_activity=ACTIVITIES.get(place.category, ACTIVITIES["attraction"])[0],
            distance_m=round(distance), distance_method=method, walking_minutes=walk_minutes,
            visit_minutes_min=visit_min, visit_minutes_max=visit_max, total_minutes=total, opening_status=status,
            caveats=caveats, maps_url=place.source_url)
        response.recommendations.append(rec)
        if len(response.recommendations) >= 3:
            break
    if not response.recommendations:
        response.summary = "Подходящие места не уложились в доступное время после проверки пути."
        return done()
    generated, warning = await generator.generate(response.recommendations, intent)
    if generated:
        selected = {r.poi.id: r for r in response.recommendations}
        response.recommendations = [selected[r.poi_id].model_copy(update={"suggested_activity": r.suggested_activity, "activity_origin": "ai"}) for r in generated.recommendations]
        response.mode = "rag" if store.semantic_ready else "lexical_only"
        response.summary = generated.summary
    else:
        response.summary = f"Нашли {len(response.recommendations)} варианта рядом. Выберите место для своей прогулки."
        if warning:
            response.warnings.append(warning)
    if any(r.distance_method == "straight_line" for r in response.recommendations):
        response.warnings.append("Пешеходный маршрут не подтверждён. Показаны отдельные места, а не гарантированный план по времени.")
    return done()


@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest):
    async with slots:
        return await recommend_impl(request)


frontend = ROOT / "frontend" / "dist"
if (frontend / "assets").exists():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")


@app.get("/")
def index():
    if (frontend / "index.html").exists():
        return FileResponse(frontend / "index.html")
    return {"name": "QADAM", "frontend": "Run Vite on http://localhost:5173 or build frontend/dist", "api_docs": "/docs"}


@app.get("/favicon.svg")
def favicon():
    path = frontend / "favicon.svg"
    if path.is_file():
        return FileResponse(path, media_type="image/svg+xml")
    raise HTTPException(404)


@app.get("/fonts/{filename}")
def fonts(filename: str):
    path = frontend / "fonts" / filename
    if path.is_file() and path.parent == frontend / "fonts":
        return FileResponse(path)
    raise HTTPException(404)
