"""Deterministic constraints. Unknown evidence never satisfies a hard constraint."""
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from functools import lru_cache
from pydantic import BaseModel, Field
from .config import BBOX, VISIT_MINUTES
from .schemas.models import Constraints, Origin, RecommendRequest


class QueryIntent(BaseModel):
    language: str = "ru"
    origin: Origin | None = None
    time_budget_minutes: int = 60
    desired_categories: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    transport_mode: str = "walking"
    party_context: str = "individual"
    hard_constraints: Constraints = Field(default_factory=Constraints)
    soft_preferences: list[str] = Field(default_factory=list)
    return_to_start: bool = False
    visit_datetime: datetime | None = None
    excluded_poi_ids: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    excluded_attributes: list[str] = Field(default_factory=list)
    required_attributes: list[str] = Field(default_factory=list)
    unsupported_preferences: list[str] = Field(default_factory=list)
    clarification: str | None = None


def haversine_m(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dlat, dlon = b-a, math.radians(lon2-lon1)
    h = math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 6371008.8 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1-h)))


def supported(origin):
    return BBOX[0] <= origin.latitude <= BBOX[2] and BBOX[1] <= origin.longitude <= BBOX[3]


def attribute_preference(query, pattern):
    """Small auditable language subset, including neutral and optional mentions."""
    term = rf"(?:{pattern})\w*"
    neutral = rf"(?:не\s+(?:нуж[а-я]*|обязател[а-я]*|требуется|важ[а-я]*)\s+(?:\w+\s+){{0,2}}{term}|{term}\s+(?:мне\s+)?не\s+(?:нуж[а-я]*|обязател[а-я]*|важ[а-я]*|требуется)|(?:don't|do not)\s+need\s+{term})"
    if re.search(neutral, query):
        return "neutral"
    if re.search(rf"(?:без\s+|no\s+){term}", query):
        return "excluded"
    if re.search(rf"(?:желатель[а-я]*|по возможности|если есть|предпочитаю|prefer)[^.!?;]{{0,70}}{term}|{term}[\s,]*(?:желатель[а-я]*|по возможности|если есть)", query):
        return "optional"
    return "required" if re.search(term, query) else None


def parse_intent(request: RecommendRequest):
    q = request.query.casefold()
    hard = request.constraints.model_copy()
    mapping = {"cafe": r"кафе|кофе|coffee|cafe|кофехана", "museum": r"музе[йяеюи]|museum", "park": r"парк|park|саябақ", "playground": r"площадк|playground", "gallery": r"галере|gallery", "theatre": r"театр|theatr"}
    desired, excluded = [], []
    for cat, pattern in mapping.items():
        if re.search(rf"(?<!\w)(?:не\s+(?:(?:хочу|нуж[а-я]*|интересу[а-я]*)\s+)?(?:ни\s+)?|без\s+|ни\s+|not\s+|no\s+|avoid\s+)(?:{pattern})", q):
            excluded.append(cat)
        elif re.search(pattern, q):
            desired.append(cat)
    if not desired:
        if request.preset == "coffee":
            desired = ["cafe"]
        elif request.preset == "family":
            desired = ["park", "playground", "museum"]
    conflicts = []
    if request.preset == "coffee" and "cafe" in excluded:
        conflicts.append("Пресет «Кофе» противоречит запрету кафе. Учитываем явный запрет.")
    if re.search(r"только\s+(?:внутри|в помещении)|indoor\s+only|only\s+indoors", q) or request.preset == "indoor":
        hard.indoor_only = True
    soft = ["less_outdoors"] if request.less_outdoors else []
    if request.preset == "walk":
        soft.append("prefer_walk")
    interests = []
    themes = {
        "quiet": r"тихо|тих[а-я]*|тишин|спокойно\s+поработ|quiet",
        "interactive": r"интерактив|interactive|hands.on",
        "photography": r"фотограф|сфотограф|фото|photograph|photo",
        "architecture": r"архитектур|architecture|здани[яй]",
        "history": r"истори[яиючес]|history|historical",
        "family": r"реб[её]н|детьми|семь[еёю]|family|children|kids",
        "night": r"(?<!\w)(?:ноч(?:ь|ью|и|ей|ам|ами|ах)|ночн(?:ой|ую|ые|ых|ым|ыми|ая|ое|ого|ому|ом)|вечер(?:ом|а|у|е|ов|ами|ах)?|вечерн(?:ий|яя|ее|ие|юю|их|им|ими|его|ему|ем|ей))\b|\bnight\b|after\s+dark",
    }
    for interest, pattern in themes.items():
        if re.search(pattern, q) and not re.search(rf"(?<!\w)(?:не\s+(?:(?:хочу|интерес[а-я]*)\s+)?|без\s+|not\s+|no\s+)(?:{pattern})", q):
            interests.append(interest)
    if request.preset == "family" and "family" not in interests:
        interests.append("family")
    required_attributes, unsupported = [], []
    for attribute in ("quiet", "interactive"):
        if attribute in interests:
            pattern = themes[attribute]
            if re.search(rf"(?:обязательно|только|непременно|must)[^.!?;]{{0,45}}(?:{pattern})", q):
                required_attributes.append(attribute)
            else:
                soft.append("prefer_" + attribute)
            unsupported.append(attribute)
    excluded_attributes = []
    for attribute, field, pattern in (
        ("sockets", "sockets_required", r"розетк|socket|power outlet"),
        ("wifi", "wifi_required", r"wi-?fi|вай.?фай"),
    ):
        preference = attribute_preference(q, pattern)
        if preference == "required":
            setattr(hard, field, True)
        elif preference == "optional":
            soft.append("prefer_" + attribute)
        elif preference == "excluded":
            excluded_attributes.append(attribute)
        if preference in {"neutral", "optional", "excluded"} and getattr(request.constraints, field):
            conflicts.append(f"Текст и обязательный фильтр «{attribute}» различаются. Снимите фильтр или уточните запрос.")
    if re.search(r"безбарьер|инвалидн|wheelchair|коляск", q):
        hard.wheelchair_required = True
    if re.search(r"без\s+(?:покупки\s+)?билет|бесплатн|free\s+only|no\s+ticket", q):
        hard.free_only = True
    if re.search(r"открыт[оы]?\s+сейчас|open\s+now", q):
        hard.open_now = True
    budget = request.time_budget_minutes
    minute_range = re.search(r"(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*(?:мин|minute|min\b)", q)
    hour_range = re.search(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*(?:час|hour)", q)
    match = re.search(r"(\d{1,3})\s*(?:мин|minute|min\b)", q)
    hour_match = re.search(r"(\d{1,2})\s*(?:час|hour)", q)
    text_budget = (
        max(map(int, minute_range.groups())) if minute_range else
        max(map(int, hour_range.groups())) * 60 if hour_range else
        int(match.group(1)) if match else
        int(hour_match.group(1)) * 60 if hour_match else
        30 if re.search(r"полчаса|полчас|half an hour", q) else
        90 if re.search(r"полтора часа", q) else
        120 if re.search(r"два\s+часа|двух\s+часов|two\s+hours", q) else
        60 if re.search(r"до\s+часа|один\s+час|one\s+hour|(?:есть|меня|провести)\s+час(?:\s|$)", q) else None
    )
    clarification = None
    if text_budget is not None:
        if text_budget != budget:
            conflicts.append(f"В тексте указано {text_budget} мин, в фильтре {budget} мин: применено меньшее значение.")
        budget = min(budget, text_budget)
        if text_budget < 10:
            clarification = "Подбор рассчитан минимум на 10 минут. У вас есть столько времени или нужно остаться на месте?"
    if any(getattr(hard, field) and attribute in excluded_attributes for attribute, field in (("wifi", "wifi_required"), ("sockets", "sockets_required"))):
        clarification = "Обязательный фильтр противоречит тексту запроса. Какое требование оставить?"
    if "night" in interests and request.visit_datetime is None:
        clarification = "На какую дату и время планируете вечернюю или ночную прогулку? Дневное расписание не подтверждает доступ ночью."
    if re.search(r"вылет|до\s+рейса|flight|аэропорт", q):
        clarification = "Где вы сейчас и к какому времени нужно быть в аэропорту? Без времени дороги и запаса прогулку до рейса не обещаем."
    if re.search(r"крыш|стройк|техническ.*проход|секретн", q):
        clarification = "Можем подобрать только публичные места без закрытых крыш и технических проходов. Подойдёт парк или публичная достопримечательность?"
    return QueryIntent(origin=request.origin, time_budget_minutes=budget, desired_categories=[c for c in desired if c not in excluded], excluded_categories=excluded,
                       interests=interests, party_context="family" if "family" in interests else "individual",
                       hard_constraints=hard, soft_preferences=soft, return_to_start=request.return_to_start or bool(re.search(r"вернуть|обратно|return", q)),
                       visit_datetime=request.visit_datetime, excluded_poi_ids=request.excluded_poi_ids, conflicts=conflicts, excluded_attributes=excluded_attributes,
                       required_attributes=required_attributes, unsupported_preferences=unsupported, clarification=clarification)


DAY = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}

@lru_cache(maxsize=8)
def holiday_dates(year):
    try:
        import holidays
        # Estimated religious dates also cause unknown, never confirmed opening.
        return holidays.country_holidays("KZ", years=year, observed=True)
    except (ImportError, ValueError, NotImplementedError):
        return None


def opening_status(raw, visit_datetime, source_updated_at=None, visit_minutes=0):
    """Conservative weekly OSM subset. PH, exceptions, overnight, old dates => unknown.
    No holiday calendar is assumed. A regular weekly rule is only source evidence.
    """
    if not raw or visit_datetime.tzinfo is None:
        return "unknown"
    if source_updated_at:
        try:
            updated = datetime.fromisoformat(source_updated_at.replace("Z", "+00:00"))
            if (visit_datetime-updated).days > 365:
                return "unknown"
        except (ValueError, TypeError):
            return "unknown"
    if raw == "24/7":
        return "open"
    local = visit_datetime.astimezone(ZoneInfo("Asia/Almaty"))
    calendar = holiday_dates(local.year)
    if calendar is None or local.date() in calendar:
        return "unknown"
    rules = []
    covered_days = set()
    for part in raw.split(";"):
        match = re.fullmatch(r"\s*(?:(Mo|Tu|We|Th|Fr|Sa|Su)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))?\s+)?(off|\d{2}:\d{2}-\d{2}:\d{2}(?:,\d{2}:\d{2}-\d{2}:\d{2})*)\s*", part)
        if not match:
            return "unknown"
        first, last, hours = match.groups()
        days = set(range(7)) if first is None else {(DAY[first]+i) % 7 for i in range(((DAY[last or first]-DAY[first]) % 7)+1)}
        # OSM override/additional-rule semantics need a full parser; no union guess.
        if covered_days & days:
            return "unknown"
        covered_days.update(days)
        intervals = []
        if hours != "off":
            for span in hours.split(","):
                a, b = span.split("-")
                ah, am = map(int, a.split(":")); bh, bm = map(int, b.split(":"))
                if ah > 23 or bh > 24 or am > 59 or bm > 59 or (bh == 24 and bm != 0):
                    return "unknown"
                start, end = ah*60+am, bh*60+bm
                if end <= start:
                    return "unknown"
                intervals.append((start, end))
        rules.append((days, intervals))
    minute = local.hour*60+local.minute
    intervals = [interval for days, spans in rules if local.weekday() in days for interval in spans]
    return "open" if any(a <= minute and minute+visit_minutes <= b and minute < b for a, b in intervals) else "closed"


def filter_candidates(pois, request, intent, now):
    if not intent.origin or not supported(intent.origin):
        return []
    hard = intent.hard_constraints
    required = {"indoor": hard.indoor_only, "wifi": hard.wifi_required, "sockets": hard.sockets_required, "wheelchair": hard.wheelchair_required, "free": hard.free_only}
    filtered = []
    for poi in pois:
        if poi.id in intent.excluded_poi_ids or poi.category in intent.excluded_categories:
            continue
        if intent.desired_categories and poi.category not in intent.desired_categories:
            continue
        if any(required[k] and poi.attributes.get(k) is not True for k in required):
            continue
        if any(poi.attributes.get(key) is not True or f"attributes.{key}" not in poi.field_provenance for key in intent.required_attributes):
            continue
        if any(poi.attributes.get(k) is not False for k in intent.excluded_attributes):
            continue
        distance = haversine_m(intent.origin.latitude, intent.origin.longitude, poi.latitude, poi.longitude)
        visit = VISIT_MINUTES.get(poi.category, (15, 30))[0]
        # A generous 5km/h straight-line lower bound only rejects impossible fits.
        # It never asserts a walkable route or a guaranteed arrival.
        lower_bound = distance / (5000/60) * (2 if intent.return_to_start else 1) + visit + 5
        if lower_bound > intent.time_budget_minutes or distance > 5000:
            continue
        status = opening_status(poi.opening_hours_raw, intent.visit_datetime or now, poi.source_updated_at, visit)
        if status == "closed" or (hard.open_now and status != "open"):
            continue
        filtered.append((poi, distance, status))
    return filtered
