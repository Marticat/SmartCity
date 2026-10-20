# QADAM — прогулка по Астане под твоё время

**Хорошая прогулка начинается рядом.** Реальные места, 1–3 объяснённых варианта, карта и строгие ограничения для прогулки, кофе и занятий с ребёнком.

Проект содержит автоматически собранные **814 POI OpenStreetMap**, локальный гибридный поиск E5 + SQLite FTS5, FastAPI, React/TypeScript и Leaflet. Данные, расчёты и идеи показаны отдельно. Без ключа Gemini работает явно обозначенный поиск без генерации. Настоящий сквозной LLM-запрос нельзя считать проверенным до подключения ключа.

Шесть мест дополнены короткими описаниями с официальных сайтов и provenance по полям. Поддерживаются интересы к истории, архитектуре, фотографии и интерактивности; тишина и услуги не обещаются без подтверждения. Для ночного/вечернего запроса можно задать дату и время Астаны в дополнительных параметрах. Режим кофе и работы поддерживает быстрый выбор 120 минут.

## Быстрый запуск

Нужны Python 3.10–3.11, Node.js 20.19+ или 22.12+, npm, интернет для первой установки и загрузки E5. Проверено на Node 20.20.2. Запускайте команды из корня проекта. Первый индекс занимает время на скачивание модели; в последующих пользовательских запросах модель не скачивается.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m scripts.collect_pois --validate
.\.venv\Scripts\python.exe -m scripts.index_pois
npm --prefix frontend ci
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --no-access-log --host 127.0.0.1 --port 8000
```

### Linux / macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
.venv/bin/python -m scripts.collect_pois --validate
.venv/bin/python -m scripts.index_pois
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python -m uvicorn backend.app.main:app --no-access-log --host 127.0.0.1 --port 8000
```

Открыть **http://127.0.0.1:8000**. После подготовки можно использовать `scripts/start.ps1` или `sh scripts/start.sh`. Для разработки: backend на 8000, `npm --prefix frontend run dev` на 5173. Vite проксирует API.

### Docker

```sh
docker compose build
docker compose run --rm qadam python -m scripts.collect_pois --validate
docker compose run --rm qadam python -m scripts.index_pois
docker compose up -d
```

Frontend собирается в отдельной стадии, один Python-контейнер обслуживает итоговый интерфейс и API. `./data` хранится вне контейнера. Docker Compose конфигурация проверяется отдельно от сборки образа: фактический статус в [verification.md](docs/verification.md).

## Переменные

| Переменная | Назначение |
|---|---|
| `GEMINI_API_KEY` | Серверный ключ реальной генерации; без него search-only |
| `LLM_MODEL` | Модель Gemini, по умолчанию `gemini-3.8-flash` |
| `ORS_API_KEY` | Необязательный ключ openrouteservice, профиль пешком |
| `WEATHER_ENABLED` | `false` отключает внешние запросы погоды |
| `DATA_DIR` | Каталог данных, по умолчанию `data/` проекта |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` |
| `EMBEDDING_REVISION` | Revision модели при подготовке; resolved SHA сохраняется в manifest |
| `FRONTEND_ORIGIN` | Разрешённый dev origin, по умолчанию `http://localhost:5173` |
| `VITE_TILE_URL` | Публичный шаблон URL подложки; применяется при frontend build |
| `VITE_TILE_ATTRIBUTION` | Публичная атрибуция выбранного провайдера тайлов; build-time |

Ключи находятся только на сервере. `.env` не коммитится. Не добавляйте ключи в `VITE_*`. Стандартная подложка OSM настроена по умолчанию; для значительной публичной нагрузки выберите разрешённого провайдера и соответствующую атрибуцию, затем пересоберите frontend.

## Обновление данных и индекса

```sh
python -m scripts.collect_pois --refresh
python -m scripts.collect_landmarks
python -m scripts.collect_pois --normalize-only
python -m scripts.collect_pois --validate
python -m scripts.index_pois
```

Используйте Python из `.venv`. Сбор и нормализация разделены; без `--refresh` используется сохранённый реальный snapshot. После обновления POI индекс надо перестроить. Режим `python -m scripts.index_pois --lexical-only` пригоден для диагностики, но не заменяет semantic retrieval. Модель и большой кэш исключены из Git.

Дополнительный сбор `scripts.collect_landmarks` сохраняет ориентиры начала прогулки (EXPO, Mega Silk Way и другие) отдельно от рекомендуемых POI. `--normalize-only` повторяет обработку сохранённого ответа без сети.

## Проверки

```sh
python -m pytest -q tests
npm --prefix frontend run typecheck
npm --prefix frontend run build
python -m scripts.benchmark --allow-dataset-update --output tests/benchmark/results-current.json
node scripts/verify-browser.cjs
node scripts/verify-resilience.cjs
node scripts/verify-context.cjs
```

Флаг `--allow-dataset-update` явно сравнивает текущий обогащённый датасет с **неизменёнными** старыми метками и записывает оба checksum. Без него benchmark отклоняет несовпадение версии. Отдельные проверки разговорных сценариев и провайдеров:

```sh
python -m scripts.evaluate_conversations
python -m scripts.check_live_readiness
```

Последние две команды разделяют проверку поведения на 17 настоящих разговорных запросах и реальные проверки провайдеров. Conversation evaluation требует запущенного приложения; live-readiness сам загружает backend и при отсутствии ключей пишет `skipped`. Субъективная полезность не оценивается моделью: для человека создаётся `tests/benchmark/human-review.csv`.

Браузерная проверка требует запущенного backend и браузера Playwright; подробности команды и результаты — в [verification.md](docs/verification.md). Тестовые fixtures живут только в `tests/`; пользовательский demo dataset настоящий.

## Демо для жюри за 3 минуты

1. Откройте приложение, выберите EXPO/ориентир из локального поиска.
2. Запросите прогулку на 60 минут. Откройте источник карточки и выделите место на карте.
3. Измените время до 30 минут: выполняется новый расчёт.
4. Выберите 120 минут и запросите интерактивный музей. Откройте официальное описание и источник подтверждённой интерактивности.
5. Попросите кофе с обязательной розеткой. В snapshot подтверждённых розеток нет: сервис объяснит отсутствие подходящих мест.
6. Посмотрите «Почему эти места» и текущий режим генерации.

Точки находятся в demo rectangle центральной Астаны и EXPO, а не по всему Казахстану. Прямое расстояние не является пешеходным маршрутом. Без routing нет гарантии времени перехода; расписание, входы и услуги могут быть неизвестны. Русский — основной язык; полноценная трёхъязычность не заявлена.

## Материалы

- [Продукт](docs/product.md), [RAG](docs/rag.md), [данные и качество](docs/data.md)
- [Контракт API](docs/api-contract.md), [сценарии](docs/test-scenarios.md), [результаты проверок](docs/verification.md)
- [Приватность и ограничения](docs/privacy-and-limitations.md), [размещение](docs/deployment.md)
- [Что конкретно осталось владельцу: ключи, проверка, публикация](docs/readiness.md)
- [Редактируемые слайды](presentation/slides.html), [заметки на 6 минут](presentation/speaker-notes.md), [PDF](presentation/QADAM.pdf)
- [Демо 2:30 с синтетической русской озвучкой](demo/QADAM-demo-narrated.mp4), [субтитры](demo/QADAM-ru.srt)
- [Сценарий и повторная сборка видео](demo/script.md), [исходная запись без звука](demo/QADAM-demo.webm)
- [Инструкция YouTube: загрузка, название, описание и таймкоды](demo/YOUTUBE_UPLOAD.md)
- [Готовый промпт для презентации на 8 слайдов](presentation/PRESENTATION_PROMPT.md)

Срез данных: 20 октября 2026, 08:38 UTC, 814 принятых из 865 исходных объектов. © OpenStreetMap contributors, ODbL 1.0. Код — MIT; лицензии данных, шрифтов и сервисов [отдельны](docs/third-party-notices.md).
