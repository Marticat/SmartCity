import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowRight, ArrowUpRight, Asterisk, Check, ChevronDown, Clock3, Coffee, Compass, Footprints, House, LocateFixed, Map, MapPin, Navigation2, RotateCcw, Search, ShieldCheck, SlidersHorizontal, Sparkles, Sun, UsersRound, Wind, X, LoaderCircle, List, Info } from 'lucide-react'
import { getDataset, getHealth, recommend, searchLocations } from './api'
import type { Constraints, DatasetStatus, Location, Origin, Preset, RecommendResponse } from './types'
import { formatDate, safeUrl } from './i18n'
import CityMap from './CityMap'
import PlaceCard from './PlaceCard'

const EMPTY_CONSTRAINTS: Constraints = { indoor_only: false, wheelchair_required: false, wifi_required: false, sockets_required: false, free_only: false, open_now: false }
const PRESETS = [
  { id: 'walk' as const, label: 'Прогуляться', icon: Footprints, query: '' },
  { id: 'coffee' as const, label: 'Кофе и ноутбук', icon: Coffee, query: 'Хочу выпить кофе и поработать.' },
  { id: 'family' as const, label: 'С ребёнком', icon: UsersRound, query: 'Хочу интересно провести время с ребёнком.' },
  { id: 'indoor' as const, label: 'В помещении', icon: House, query: 'Хочу провести время только в помещении.' },
]
const EXAMPLES = [
  { id: 'quiet-coffee', title: 'Тихий кофе', subtitle: 'Поработать без спешки', icon: Coffee, preset: 'coffee' as const, minutes: 60,
    query: 'Хочу выпить кофе и спокойно поработать. Желательно Wi-Fi. Желательны розетки.',
    note: 'Тишина и свободные столики не подтверждены. Wi-Fi и розетки — пожелания; обязательными их делают отдельные фильтры.' },
  { id: 'family', title: 'Час с ребёнком', subtitle: 'Парк, площадка или музей', icon: UsersRound, preset: 'family' as const, minutes: 60,
    query: 'Хочу интересно провести время с ребёнком.',
    note: 'Возраст ребёнка и интересы можно дописать. Наличие подходящих услуг проверяй в сведениях о месте.' },
  { id: 'architecture', title: 'Архитектура города', subtitle: 'Два часа для знакомства', icon: Compass, preset: 'walk' as const, minutes: 120,
    query: 'Я турист: хочу посмотреть архитектуру и достопримечательности, без кафе.',
    note: '120 минут — бюджет на прогулку. Без пешего маршрута время переходов остаётся непроверенным.' },
  { id: 'expo', title: 'Час у EXPO', subtitle: 'Начать с реального ориентира', icon: MapPin, preset: 'walk' as const, minutes: 60,
    query: 'Я возле EXPO. Хочу прогуляться и посмотреть интересные места.',
    note: 'Начальная точка берётся из локального каталога OpenStreetMap. В подборке — отдельные варианты рядом.' },
]
const FILTERS: { id: keyof Constraints; name: string }[] = [
  { id: 'wifi_required', name: 'Обязателен Wi-Fi' }, { id: 'sockets_required', name: 'Нужна розетка' },
  { id: 'wheelchair_required', name: 'Доступность на коляске' }, { id: 'free_only', name: 'Без платы за вход' },
  { id: 'open_now', name: 'Подтверждённо открыто' }, { id: 'indoor_only', name: 'Только в помещении' },
]
export default function App() {
  const [dataset, setDataset] = useState<DatasetStatus | null>(null)
  const [llmConfigured, setLlmConfigured] = useState(false)
  const [landmarks, setLandmarks] = useState<Location[]>([])
  const [locationResults, setLocationResults] = useState<Location[]>([])
  const [locationSearch, setLocationSearch] = useState('')
  const [locationOpen, setLocationOpen] = useState(false)
  const [locationLoading, setLocationLoading] = useState(false)
  const [activeLocation, setActiveLocation] = useState(-1)
  const [exampleNote, setExampleNote] = useState('')
  const [origin, setOrigin] = useState<Origin | null>(null)
  const [query, setQuery] = useState('')
  const [time, setTime] = useState(60)
  const [preset, setPreset] = useState<Preset>('walk')
  const [constraints, setConstraints] = useState<Constraints>({ ...EMPTY_CONSTRAINTS })
  const [returnToStart, setReturnToStart] = useState(false)
  const [lessOutdoors, setLessOutdoors] = useState(false)
  const [visitWhen, setVisitWhen] = useState<'now' | 'scheduled'>('now')
  const [visitDatetime, setVisitDatetime] = useState('')
  const [response, setResponse] = useState<RecommendResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [locationError, setLocationError] = useState('')
  const [geoLoading, setGeoLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [picking, setPicking] = useState(false)
  const [mobileView, setMobileView] = useState('list')
  const [modal, setModal] = useState<'about' | 'privacy' | null>(null)
  const controller = useRef<AbortController | null>(null)
  const locationController = useRef<AbortController | null>(null)
  const locationRequestVersion = useRef(0)
  const submitted = useRef(false)
  const requestVersion = useRef(0)
  const resultsRef = useRef<HTMLDivElement>(null)
  const plannerRef = useRef<HTMLFormElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  const modalRef = useRef<HTMLDialogElement>(null)

  const bootstrap = useCallback(async () => {
    try {
      const [status, locations, health] = await Promise.all([getDataset(), searchLocations(''), getHealth()])
      setDataset(status); setLandmarks(locations.locations)
      setLlmConfigured(health.llm_configured); setError('')
    } catch { setError('Сервис пока недоступен. Убедись, что сервер запущен, и повтори подключение.') }
  }, [])
  useEffect(() => { void bootstrap(); return () => { controller.current?.abort() } }, [bootstrap])
  useEffect(() => {
    if (!locationOpen) return
    const abort = new AbortController()
    locationController.current = abort
    const version = ++locationRequestVersion.current
    setLocationLoading(true)
    const timer = window.setTimeout(async () => {
      try {
        const data = await searchLocations(locationSearch, abort.signal)
        if (abort.signal.aborted || version !== locationRequestVersion.current) return
        setLocationResults(data.locations); setActiveLocation(-1)
      }
      catch (err) {
        if (!abort.signal.aborted && version === locationRequestVersion.current && !(err instanceof DOMException && err.name === 'AbortError'))
          setLocationError('Поиск ориентира недоступен. Можно выбрать точку на карте.')
      }
      finally { if (!abort.signal.aborted && version === locationRequestVersion.current) setLocationLoading(false) }
    }, 250)
    return () => { clearTimeout(timer); abort.abort() }
  }, [locationSearch, locationOpen])

  const runSearch = useCallback(async (scroll = false) => {
    if (!origin) { setLocationError('Выбери отправную точку — ориентир, свою геопозицию или место на карте.'); setLocationOpen(true); return }
    if (visitWhen === 'scheduled' && !visitDatetime) { setError('Выбери дату и время прогулки или верни вариант «Сейчас».'); return }
    submitted.current = true
    controller.current?.abort()
    const abort = new AbortController(); controller.current = abort
    const version = ++requestVersion.current
    setLoading(true); setError('')
    try {
      const result = await recommend({
        query, origin, time_budget_minutes: time, preset, constraints, return_to_start: returnToStart,
        less_outdoors: lessOutdoors, excluded_poi_ids: [],
        // datetime-local is a wall-clock value in Astana, regardless of the browser's timezone.
        visit_datetime: visitWhen === 'scheduled' ? `${visitDatetime}+05:00` : null,
      }, abort.signal)
      if (version !== requestVersion.current || abort.signal.aborted) return
      setResponse(result); setDataset(result.dataset); setSelected(result.recommendations[0]?.poi.id || null)
      if (scroll) window.setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    } catch (err) {
      if (!abort.signal.aborted && version === requestVersion.current) {
        setError(err instanceof Error ? err.message : 'Что-то пошло не так. Попробуй ещё раз.')
        setResponse(null); setSelected(null)
      }
    } finally { if (version === requestVersion.current && !abort.signal.aborted) setLoading(false) }
  }, [origin, query, time, preset, constraints, returnToStart, lessOutdoors, visitWhen, visitDatetime])
  useEffect(() => {
    if (!submitted.current) return
    controller.current?.abort(); ++requestVersion.current; setLoading(true)
    if (!origin) { setLoading(false); return }
    if (visitWhen === 'scheduled' && !visitDatetime) { setLoading(false); setResponse(null); setSelected(null); return }
    const timer = window.setTimeout(() => { void runSearch() }, 450)
    return () => clearTimeout(timer)
  }, [runSearch, origin, visitWhen, visitDatetime])
  useEffect(() => {
    if (modal) modalRef.current?.showModal()
    else modalRef.current?.close()
  }, [modal])

  function chooseLocation(location: Location) {
    setOrigin({ latitude: location.latitude, longitude: location.longitude, label: location.name })
    setLocationSearch(location.name); setLocationOpen(false); setLocationError(''); setPicking(false); setActiveLocation(-1)
  }
  function geolocate() {
    if (!navigator.geolocation) { setLocationError('Геолокация недоступна. Найди ориентир или выбери точку на карте.'); return }
    setGeoLoading(true); setLocationError('')
    navigator.geolocation.getCurrentPosition(position => {
      setOrigin({ latitude: position.coords.latitude, longitude: position.coords.longitude, label: 'Моё местоположение' })
      setLocationSearch('Моё местоположение'); setLocationOpen(false); setGeoLoading(false)
    }, () => {
      setGeoLoading(false); setLocationError('Не удалось получить геопозицию. Выбери ориентир или точку на карте — разрешение не обязательно.')
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 120000 })
  }
  function reset() {
    submitted.current = false; ++requestVersion.current; controller.current?.abort()
    ++locationRequestVersion.current; locationController.current?.abort()
    setOrigin(null); setLocationSearch(''); setQuery(''); setTime(60); setPreset('walk')
    setConstraints({ ...EMPTY_CONSTRAINTS }); setLessOutdoors(false); setReturnToStart(false)
    setVisitWhen('now'); setVisitDatetime('')
    setResponse(null); setSelected(null); setLoading(false); setError(''); setLocationError('')
    setPicking(false); setLocationOpen(false); setLocationResults([]); setLocationLoading(false); setMobileView('list')
    setExampleNote(''); setActiveLocation(-1)
    sidebarRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
    if (window.innerWidth < 800) window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  function choosePreset(id: Preset) {
    setPreset(id); setQuery(PRESETS.find(item => item.id === id)!.query)
    setExampleNote('')
    setConstraints(current => ({ ...current, indoor_only: id === 'indoor' }))
  }
  function chooseExample(example: typeof EXAMPLES[number]) {
    setQuery(example.query); setPreset(example.preset); setTime(example.minutes); setExampleNote(example.note)
    if (example.id === 'expo') {
      const expo = landmarks.find(location => /^EXPO$/i.test(location.name.trim()))
      if (expo) chooseLocation(expo)
      else {
        ++locationRequestVersion.current; locationController.current?.abort(); setLocationResults([]); setLocationLoading(true)
        setOrigin(null); setResponse(null); setSelected(null); setLocationSearch('EXPO'); setLocationOpen(true)
        setLocationError('Выбери EXPO из найденных ориентиров: координаты берём только из каталога.')
      }
    }
  }
  function selectPlace(id: string, fromMap = false) {
    setSelected(id)
    if (fromMap) {
      setMobileView('list')
      window.setTimeout(() => document.getElementById(`place-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
    } else if (window.innerWidth < 800) setMobileView('map')
  }
  const activeFilters = Object.values(constraints).filter(Boolean).length
  const mode = response?.mode || (llmConfigured && dataset?.semantic_ready ? 'rag' : dataset?.semantic_ready ? 'search_only' : 'lexical_only')
  const modeText = mode === 'rag' ? (response ? 'ИИ + реальные данные' : 'ИИ настроен · поиск по данным') : mode === 'lexical_only' ? 'Текстовый поиск · без ИИ' : mode === 'test' ? 'Тестовые данные' : 'Поиск · без генерации'
  const recs = response?.recommendations || []
  const appliedTime = response?.trace.applied_constraints.find(value => /^Время: \d+ мин/.test(value))?.match(/\d+/)?.[0] || time
  return <div className="app-shell">
    <header className="site-header">
      <a className="wordmark" href="/" aria-label="QADAM — на главную"><span className="brand-symbol"><Navigation2 size={23} fill="currentColor" /></span>qadam<span className="brand-dot">.</span></a>
      <div className="header-tagline">Хорошая прогулка<br />начинается рядом</div>
      <div className="header-right"><span className="city-pill"><span />Астана</span><button onClick={() => setModal('about')}>Как это работает<ArrowUpRight size={15} /></button><span className="header-edition">ГОРОД В ТВОЁМ РИТМЕ</span></div>
    </header>
    <main className={`workspace view-${mobileView}`}>
      <aside className="sidebar" ref={sidebarRef} aria-label="Подбор прогулки">
        <div className="intro">
          <div className="intro-kicker"><span>ТВОЙ ЛИЧНЫЙ ГОРОДСКОЙ ГИД</span><Compass size={17} /></div>
          <h1>Есть время.<br />Есть <span>куда пойти.</span><Asterisk className="heading-star" aria-hidden="true" size={47} strokeWidth={1.7} /></h1>
          <p>Расскажи, чего хочется. Найдём интересное<br className="desktop-br" /> рядом и подстроимся под твой день.</p>
        </div>
        <form className="planner" ref={plannerRef} onSubmit={event => { event.preventDefault(); setMobileView('list'); void runSearch(true) }}>
          <div className="field-heading"><label htmlFor="location">Откуда начнём?</label><button type="button" className="text-button" onClick={geolocate} disabled={geoLoading}>
            {geoLoading ? <LoaderCircle size={14} className="spin" /> : <LocateFixed size={14} />}Моя геопозиция</button></div>
          <div className="location-wrap">
            <div className={`location-input ${locationOpen ? 'focused' : ''}`}><MapPin size={19} />
              <input id="location" data-testid="location-search" autoComplete="off" placeholder="Найти место или ориентир"
                value={locationSearch} onFocus={() => {
                  if (!locationOpen) { setLocationResults([]); setLocationLoading(true); setActiveLocation(-1) }
                  setLocationOpen(true)
                }}
                onChange={e => {
                  ++locationRequestVersion.current; locationController.current?.abort()
                  setLocationSearch(e.target.value); setLocationResults([]); setLocationLoading(true)
                  setOrigin(null); setResponse(null); setSelected(null); setLocationOpen(true); setActiveLocation(-1)
                }}
                onKeyDown={e => {
                  if (e.key === 'Escape') { setLocationOpen(false); setActiveLocation(-1) }
                  if (e.key === 'ArrowDown') { e.preventDefault(); setLocationOpen(true); setActiveLocation(current => Math.min(current + 1, locationResults.length - 1)) }
                  if (e.key === 'ArrowUp') { e.preventDefault(); setActiveLocation(current => Math.max(0, current - 1)) }
                  if (e.key === 'Enter' && locationOpen && activeLocation >= 0 && locationResults[activeLocation]) {
                    e.preventDefault(); chooseLocation(locationResults[activeLocation])
                  }
                }}
                aria-expanded={locationOpen} aria-controls={locationOpen ? 'location-options' : undefined} role="combobox"
                aria-autocomplete="list" aria-activedescendant={locationOpen && activeLocation >= 0 ? `location-option-${activeLocation}` : undefined}
                aria-invalid={!!locationError} aria-describedby={locationError ? 'location-error' : undefined} />
              {origin ? <Check size={17} className="green" /> : <Search size={16} />}
            </div>
            {locationOpen && <><button className="dropdown-backdrop" type="button" aria-label="Закрыть выбор локации" onClick={() => setLocationOpen(false)} />
              <div className="location-dropdown" id="location-options" role="listbox" aria-label="Найденные ориентиры">
                <span className="dropdown-label">{locationLoading ? 'Ищем в местном каталоге…' : 'ОРИЕНТИРЫ ИЗ OPENSTREETMAP'}</span>
                {!locationLoading && !locationResults.length && <p>Такого ориентира нет в каталоге. Выбери точку на карте.</p>}
                {locationResults.map((location, index) => <button type="button" key={location.id} id={`location-option-${index}`} data-testid="location-option" role="option" className={activeLocation === index ? 'keyboard-active' : ''} aria-selected={activeLocation === index || origin?.label === location.name} onClick={() => chooseLocation(location)}><MapPin size={15} /><span>{location.name}</span><ArrowUpRight size={14} /></button>)}
                <button className="dropdown-map" type="button" onClick={() => { setLocationOpen(false); setPicking(true); setMobileView('map') }}><Map size={15} />Выбрать точку на карте<ArrowRight size={15} /></button>
              </div></>}
          </div>
          {locationError && <p className="field-error" id="location-error" role="alert">{locationError}</p>}
          {!origin && !locationOpen && landmarks.length > 0 && <div className="location-suggestions"><span>Например:</span>{landmarks.slice(0, 2).map(place => <button type="button" key={place.id} onClick={() => chooseLocation(place)} title={place.name}>{place.name}</button>)}</div>}
          <div className="field-heading query-heading"><label htmlFor="query">На что у тебя есть время?</label><span>Своими словами</span></div>
          <textarea id="query" data-testid="query-input" value={query} maxLength={1000} onChange={e => { setQuery(e.target.value); setExampleNote('') }} placeholder="Хочу немного прогуляться, а потом согреться за кофе…" rows={2} />
          <div className="preset-grid">{PRESETS.map(({ id, label, icon: Icon }) =>
            <button type="button" className={`preset ${preset === id ? 'active' : ''}`} aria-pressed={preset === id} onClick={() => choosePreset(id)} key={id}><Icon size={17} />{label}</button>)}</div>
          <details className="query-examples"><summary><Sparkles size={14} />Попробовать готовый запрос<ChevronDown size={14} /></summary>
            <div className="example-grid">{EXAMPLES.map(example => <button type="button" key={example.id} data-testid={`example-${example.id}`} onClick={() => chooseExample(example)}>
              <example.icon size={16} /><span><strong>{example.title}</strong><small>{example.subtitle}</small></span><ArrowUpRight size={13} />
            </button>)}</div><p>Заполним пожелание и время. Твои обязательные фильтры сохранятся.</p>
          </details>
          {exampleNote && <p className="example-note" role="status"><Info size={13} />{exampleNote}</p>}
          <div className="time-row"><div><Clock3 size={17} /><span>У меня есть</span></div><div className="time-options" role="group" aria-label="Доступное время">{[30, 60, 90, 120].map(minutes =>
            <button key={minutes} type="button" data-testid={`time-${minutes}`} className={time === minutes ? 'active' : ''} aria-pressed={time === minutes} aria-label={`${minutes} минут`} onClick={() => setTime(minutes)}>{minutes}<span> мин</span></button>)}</div></div>
          <div className="quick-preferences">
            <label><input type="checkbox" checked={returnToStart} onChange={e => setReturnToStart(e.target.checked)} /><span className="custom-check"><Check size={12} /></span>Вернуться к началу</label>
            <label><input type="checkbox" checked={lessOutdoors} onChange={e => setLessOutdoors(e.target.checked)} /><span className="custom-check"><Check size={12} /></span>Меньше на улице</label>
          </div>
          <details className="filters"><summary><SlidersHorizontal size={15} />Что ещё важно{activeFilters > 0 && <span className="filter-count">{activeFilters}</span>}{visitWhen === 'scheduled' && <Clock3 size={13} aria-label="Выбрано время визита" />}<ChevronDown size={15} /></summary>
            <p>Обязательные условия: если подтверждения нет, место не попадёт в подборку.</p>
            <div>{FILTERS.map(filter => <label key={filter.id}><input type="checkbox" checked={constraints[filter.id]} onChange={e => setConstraints(current => ({ ...current, [filter.id]: e.target.checked }))} />{filter.name}</label>)}</div>
            <section className="visit-time" aria-label="Когда пойдём">
              <div className="visit-time-heading"><span>Когда пойдём</span><div role="group" aria-label="Время прогулки">
                <button type="button" data-testid="visit-now" aria-pressed={visitWhen === 'now'} onClick={() => { setVisitWhen('now'); setError('') }}>Сейчас</button>
                <button type="button" data-testid="visit-scheduled" aria-pressed={visitWhen === 'scheduled'} onClick={() => { setVisitWhen('scheduled'); setError('') }}>Выбрать время</button>
              </div></div>
              {visitWhen === 'scheduled' && <div className="visit-time-input">
                <label htmlFor="visit-datetime">Дата и время в Астане</label>
                <input id="visit-datetime" data-testid="visit-datetime" type="datetime-local" value={visitDatetime}
                  required step={60} aria-describedby="visit-time-note" onChange={event => { setVisitDatetime(event.target.value); setError('') }} />
                <p id="visit-time-note">Вводи местное время Астаны. Для будущей прогулки прогноз и часы работы могут быть неизвестны — покажем это в результате.</p>
              </div>}
            </section>
          </details>
          <button type="submit" className="submit-button" data-testid="submit-recommend" disabled={loading}>
            {loading ? <><LoaderCircle className="spin" size={19} /><span>Подбираем места…</span></> : <><span>Подобрать прогулку</span><ArrowUpRight size={23} /></>}
          </button>
          <div className="mode-note"><span className={`status-dot ${mode === 'rag' ? 'live' : ''}`} />{modeText}<button type="button" onClick={() => setModal('about')} aria-label="О режиме поиска"><Info size={13} /></button></div>
        </form>
        <div className="results" ref={resultsRef} aria-live="polite" aria-busy={loading}>
          {error && <div className="error-box" role="alert"><Info size={19} /><div><strong>Не получилось загрузить</strong><p>{error}</p><button onClick={() => { if (submitted.current) void runSearch(); else void bootstrap() }}>Повторить<RotateCcw size={13} /></button></div></div>}
          {loading && <div className="loading-state"><div className="loading-line" /><span>Запрос отправлен. Проверяем реальные места и ограничения.</span></div>}
          {response && <div className={loading ? 'results-content pending' : 'results-content'}>
            <div className="results-heading"><div><span className="eyebrow">ТВОИ ПЛАНЫ НА {appliedTime} МИНУТ</span><h2>{recs.length ? 'Вот куда можно.' : 'Пока без совпадений.'}</h2></div><span className="result-count">{String(recs.length).padStart(2, '0')}</span></div>
            <p className="results-summary">{response.summary}</p>
            {visitWhen === 'scheduled' && visitDatetime && <p className="visit-context"><Clock3 size={13} />
              Визит: {new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }).format(new Date(`${visitDatetime}+05:00`))} · время Астаны
            </p>}
            {response.clarifying_question && <div className="clarification"><Info size={17} />{response.clarifying_question}</div>}
            {response.weather.status === 'available' ? <div className="weather"><Sun size={17} /><strong>{response.weather.temperature_c}°</strong><Wind size={16} />{response.weather.wind_kmh} км/ч<span>{response.weather.observed_at ? new Date(response.weather.observed_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }) : ''}</span><a href={safeUrl(response.weather.source_url)} target="_blank" rel="noopener noreferrer">Open-Meteo<ArrowUpRight size={12} /></a></div>
              : <p className="weather-unavailable"><Wind size={14} />Погода сейчас недоступна — проверь перед выходом.</p>}
            {response.warnings.length > 0 && <details className="warnings"><summary><Info size={14} />Что учесть перед выходом <span>{response.warnings.length}</span><ChevronDown size={14} /></summary><ul>{response.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
            {recs.map((item, index) => <PlaceCard key={item.poi.id} item={item} index={index} selected={selected === item.poi.id} onSelect={() => selectPlace(item.poi.id)} wheelchairRequired={response.trace.applied_constraints.includes('wheelchair_required')} />)}
            {!recs.length && <div className="empty-results"><Compass size={35} /><h3>Попробуем чуть иначе?</h3><p>Увеличь время, выбери другой ориентир или сними одно обязательное условие. Неизвестные свойства мы не считаем подтверждёнными.</p><button onClick={() => { setConstraints({ ...EMPTY_CONSTRAINTS }); setQuery(''); setPreset('walk') }}>Убрать ограничения<ArrowRight size={15} /></button></div>}
            <details className="trace"><summary><Sparkles size={15} />Почему эти места<ChevronDown size={15} /></summary><div>
              <p>Это фактический журнал поиска, а не внутренние рассуждения модели.</p>
              <dl><div><dt>Кандидатов</dt><dd>{response.trace.candidate_count}</dd></div><div><dt>После фильтрации</dt><dd>{response.trace.filtered_count}</dd></div><div><dt>Метод поиска</dt><dd>{response.trace.retrieval_method}</dd></div><div><dt>Время обработки</dt><dd>{(response.trace.elapsed_ms / 1000).toFixed(2)} с</dd></div></dl>
              <p><strong>Применены:</strong> {response.trace.applied_constraints.join(', ') || 'базовые параметры запроса'}.</p>
              <p><strong>Источники:</strong> {response.trace.sources.join(', ') || response.dataset.source}.</p>
              <p><strong>Режим:</strong> {modeText}. {response.mode !== 'rag' ? 'Объяснения и идеи в карточках сформированы по шаблону.' : 'ИИ формулирует объяснения и предлагает занятия по найденным местам. Сервер проверяет формат ответа, идентификаторы мест и ссылки на поля источников. Такая проверка не гарантирует достоверность каждой фразы ИИ.'}</p>
            </div></details>
            <button className="back-to-form" onClick={() => plannerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>Изменить пожелания<ArrowUpRight size={15} /></button>
          </div>}
          {!response && !loading && <div className="initial-note"><div className="initial-note-icon"><Footprints size={25} /></div><div><h3>Не маршрут на весь день.<br />Маленький план для тебя.</h3><p>До трёх подходящих мест. С объяснениями,<br />реальными источниками и без спешки.</p></div><ArrowDown size={20} className="note-arrow" /></div>}
        </div>
        <footer className="sidebar-footer"><div><ShieldCheck size={14} /><button onClick={() => setModal('privacy')}>Твоя локация — только для поиска</button></div>
          <div><span>{dataset?.ready ? `${dataset.poi_count} мест · OpenStreetMap` : 'Данные OpenStreetMap'}{dataset?.stale ? ' · требуют обновления' : ''}</span><button data-testid="reset-session" onClick={reset} title="Очистить эту сессию"><RotateCcw size={13} />Сбросить</button></div>
          {dataset?.collected_at && <span className="dataset-date">Данные собраны {formatDate(dataset.collected_at)}</span>}
        </footer>
      </aside>
      <CityMap origin={origin} landmarks={landmarks} recommendations={recs} selected={selected} picking={picking}
        mobileView={mobileView} onSelect={id => selectPlace(id, true)} onLocation={chooseLocation}
        onPicking={() => { setPicking(!picking); setMobileView('map') }}
        onPick={point => { setOrigin(point); setLocationSearch(point.label || 'Точка на карте'); setPicking(false); setLocationError(''); setMobileView('list') }} />
    </main>
    <nav className="mobile-tabs" aria-label="Вид приложения"><button className={mobileView === 'list' ? 'active' : ''} aria-pressed={mobileView === 'list'} data-testid="mobile-list" onClick={() => setMobileView('list')}><List size={18} />Список{recs.length > 0 && <span>{recs.length}</span>}</button><button className={mobileView === 'map' ? 'active' : ''} aria-pressed={mobileView === 'map'} data-testid="mobile-map" onClick={() => setMobileView('map')}><Map size={18} />Карта</button></nav>
    <dialog ref={modalRef} className="info-modal" aria-labelledby="info-modal-title" onCancel={() => setModal(null)} onClick={event => { if (event.target === modalRef.current) setModal(null) }}>
      <button className="close-modal" aria-label="Закрыть" onClick={() => setModal(null)}><X size={21} /></button>
      <div className="modal-symbol">{modal === 'privacy' ? <ShieldCheck size={27} /> : <Compass size={27} />}</div>
      <span className="eyebrow">QADAM · ЧЕСТНО О ГЛАВНОМ</span>
      <h2 id="info-modal-title">{modal === 'privacy' ? 'Твой город.\nТвоя приватность.' : 'Меньше поиска.\nБольше прогулок.'}</h2>
      {modal === 'privacy' ? <><p>Геопозиция необязательна. Можно выбрать ориентир или точку на карте. Запрос и координаты используются сервером для текущего подбора; история поиска и точная локация не сохраняются в приложении.</p><p>Карта загружает тайлы OpenStreetMap: провайдер видит IP и просматриваемую область. Погода запрашивается для округлённых координат. Если подключён пеший маршрут, его провайдер получает координаты начала и назначения.</p><p>При включённом ИИ провайдер модели получает выделенные категории, предпочтения и сведения о найденных местах. Исходный текст запроса и точная геопозиция модели не передаются.</p><button className="modal-action" onClick={() => { reset(); setModal(null) }}>Очистить текущую сессию<RotateCcw size={16} /></button></>
        : <><p>Выбери, откуда начнёшь, сколько есть времени и чего хочется. QADAM найдёт до трёх реальных мест в локальном каталоге Астаны.</p><ol><li><strong>Сначала — данные.</strong> Места собраны из OpenStreetMap. Источник и дата доступны в каждой карточке.</li><li><strong>Затем — твои условия.</strong> География, время и обязательные свойства ограничивают поиск. Неизвестные удобства не считаются подтверждёнными.</li><li><strong>В конце — понятный выбор.</strong> Названия, координаты и расчётные значения берутся из данных и кода. Объяснения и занятия могут быть предложением ИИ.</li></ol><p className="modal-mode"><span className="status-dot" />Текущий режим: {modeText}. {mode !== 'rag' ? 'В этом режиме используются реальные данные и шаблоны без генерации ИИ.' : 'Сервер проверяет структуру ответа, идентификаторы мест и ссылки на поля источников. Это не полная проверка достоверности каждой фразы модели.'}</p><p>Без маршрутного провайдера расстояние показано по прямой: это не готовый пеший маршрут и не обещание уложиться в срок.</p></>}
    </dialog>
  </div>
}
