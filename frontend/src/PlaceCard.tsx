import { ArrowUpRight, Clock3, ExternalLink, MapPin, ShieldCheck, Sparkles, ChevronDown, Info } from 'lucide-react'
import type { Recommendation } from './types'
import { categoryName, evidenceName, formatDate, ru, safeUrl } from './i18n'

function provenance(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  return {
    url: typeof record.source_url === 'string' ? safeUrl(record.source_url) : undefined,
    name: typeof record.source_name === 'string' ? record.source_name : 'Источник сведений',
    collected: typeof record.collected_at === 'string' ? record.collected_at : null,
  }
}

export default function PlaceCard({ item, index, selected, onSelect, wheelchairRequired = false }: {
  item: Recommendation; index: number; selected: boolean; onSelect: () => void; wheelchairRequired?: boolean
}) {
  const { poi } = item
  const descriptionSource = provenance(poi.field_provenance.description)
  const officialDescription = poi.description_origin === 'official_source_summary'
  const attributeSources = Object.entries(poi.field_provenance).flatMap(([key, value]) => {
    if (!key.startsWith('attributes.')) return []
    const source = provenance(value)
    return source?.url && source.url !== safeUrl(poi.source_url)
      ? [{ key, label: evidenceName(key), ...source }] : []
  })
  const distance = item.distance_m >= 1000 ? `${(item.distance_m / 1000).toFixed(1)} км` : `${Math.round(item.distance_m)} м`
  // API caveats are authoritative. Collapse only messages already shown explicitly.
  const caveats = [...new Set(item.caveats.map(caveat => caveat.trim()))].filter(caveat => {
    if (item.opening_status === 'unknown' && /часы работы.*не подтверждены/i.test(caveat)) return false
    if (item.distance_method === 'straight_line' && /расстояние по прямой.*путь и время перехода не проверены/i.test(caveat)) return false
    return true
  })
  const isCoordinateDetail = (caveat: string) => /центр объекта.*вход/i.test(caveat)
  const isAccessibilityDetail = (caveat: string) => /безбарьерность всего пути/i.test(caveat) && !wheelchairRequired
  const visibleCaveats = caveats.filter(caveat => !isCoordinateDetail(caveat) && !isAccessibilityDetail(caveat))
  const detailCaveats = caveats.filter(isAccessibilityDetail)
  return <article className={`place-card ${selected ? 'selected' : ''}`} id={`place-${poi.id}`}
    data-testid="recommendation-card" data-selected={selected}>
    <div className="place-top">
      <button className="place-number" onClick={onSelect} aria-label={`Выбрать на карте: ${poi.name}`}>{String(index + 1).padStart(2, '0')}</button>
      <div className="place-title"><span className="eyebrow">{categoryName(poi.category)}</span>
        <button onClick={onSelect}><h3>{poi.name}</h3></button></div>
      <button className="card-map-icon" onClick={onSelect} title="Показать на карте" aria-label={`На карте: ${poi.name}`}><ArrowUpRight size={22} /></button>
    </div>
    <div className="place-metrics"><span><MapPin size={14} />{distance} {item.distance_method === 'straight_line' ? 'по прямой' : 'пешком'}</span>
      <span><Clock3 size={14} />{item.visit_minutes_min}–{item.visit_minutes_max} мин на месте</span></div>
    <p className="place-why"><span className="explanation-label">{item.activity_origin === 'ai' ? 'ПОЧЕМУ ПОДОЙДЁТ · ОБЪЯСНЕНИЕ ИИ' : 'ПОЧЕМУ ПОДОЙДЁТ · ПО ДАННЫМ'}</span>{item.why_suitable}</p>
    <div className="activity"><Sparkles size={16} /><div><span>{item.activity_origin === 'ai' ? 'ИДЕЯ ИИ' : 'ИДЕЯ ДЛЯ ПРОГУЛКИ · ШАБЛОН'}</span><p>{item.suggested_activity}</p></div></div>
    <div className="place-known">
      <span className={item.opening_status === 'open' ? 'verified' : 'unknown'}>{item.opening_status === 'open' ? 'Открыто по данным расписания' : item.opening_status === 'closed' ? 'Закрыто по данным расписания' : 'Часы работы не подтверждены'}</span>
      {item.distance_method === 'straight_line' && <p>Путь и время перехода не проверены; уложиться в бюджет не гарантируем.</p>}
      {item.walking_minutes !== null && <p>Пешком: ~{Math.round(item.walking_minutes)} мин{item.total_minutes !== null ? ` · всего ~${Math.ceil(item.total_minutes)} мин` : ''}.</p>}
      {visibleCaveats.map((caveat, i) => <p key={i}><Info size={12} />{caveat}</p>)}
    </div>
    <details className="source-details"><summary><ShieldCheck size={14} />Источники и сведения<ChevronDown size={14} /></summary>
      <div className="source-body">
        <p><strong>{officialDescription ? 'Краткое описание по официальному источнику:' : 'По данным OSM:'}</strong> {poi.description || categoryName(poi.category)}</p>
        {descriptionSource?.url && <div className="provenance-reference">
          <a href={descriptionSource.url} target="_blank" rel="noopener noreferrer">{descriptionSource.name}<ExternalLink size={12} /></a>
          <span>Описание получено: {formatDate(descriptionSource.collected)}</span>
        </div>}
        {poi.address && <p><strong>Адрес:</strong> {poi.address}</p>}
        <p><strong>Расписание:</strong> {poi.opening_hours_raw || 'нет данных'}</p>
        <dl className="attributes">{Object.entries(ru.attributes).map(([key, label]) =>
          <div key={key}><dt>{label}</dt><dd>{poi.attributes[key] === true ? 'Подтверждено' : poi.attributes[key] === false ? 'Нет' : 'Нет данных'}</dd></div>)}</dl>
        {attributeSources.map(source => <div className="provenance-reference" key={source.key}>
          <span>{source.label}:</span><a href={source.url} target="_blank" rel="noopener noreferrer">{source.name}<ExternalLink size={12} /></a>
          <span>Получено: {formatDate(source.collected)}</span>
        </div>)}
        <p>Данные OSM загружены: {formatDate(poi.collected_at)}. Это дата сбора, не подтверждение заведением.</p>
        <p>Изменение в OSM: {formatDate(poi.source_updated_at)}.</p>
        <p>Координаты: {poi.coordinate_kind === 'node' || poi.coordinate_kind === 'point' ? 'точка объекта' : 'центр объекта; вход может находиться в другом месте'}.</p>
        {detailCaveats.map(caveat => <p key={caveat}>{caveat}</p>)}
        {!!item.evidence_field_ids.length && <p>Основание для объяснения: {[...new Set(item.evidence_field_ids.map(evidenceName))].join(', ')}.</p>}
        <a href={safeUrl(poi.source_url)} target="_blank" rel="noopener noreferrer">Запись OpenStreetMap<ExternalLink size={13} /></a>
      </div>
    </details>
    <div className="place-actions"><button onClick={onSelect}>На карте<MapPin size={14} /></button>
      <a href={safeUrl(item.maps_url)} target="_blank" rel="noopener noreferrer">Открыть в картах<ExternalLink size={14} /></a></div>
  </article>
}
