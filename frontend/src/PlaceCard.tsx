import { ArrowUpRight, Clock3, ExternalLink, MapPin, ShieldCheck, Sparkles, ChevronDown, Info } from 'lucide-react'
import type { Recommendation } from './types'
import { categoryName, formatDate, ru, safeUrl } from './i18n'

export default function PlaceCard({ item, index, selected, onSelect, wheelchairRequired = false }: {
  item: Recommendation; index: number; selected: boolean; onSelect: () => void; wheelchairRequired?: boolean
}) {
  const { poi } = item
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
    <p className="place-why">{item.why_suitable}</p>
    <div className="activity"><Sparkles size={16} /><div><span>{item.activity_origin === 'ai' ? 'ИДЕЯ ИИ' : 'ИДЕЯ ДЛЯ ПРОГУЛКИ · ШАБЛОН'}</span><p>{item.suggested_activity}</p></div></div>
    <div className="place-known">
      <span className={item.opening_status === 'open' ? 'verified' : 'unknown'}>{item.opening_status === 'open' ? 'Открыто по данным расписания' : item.opening_status === 'closed' ? 'Закрыто по данным расписания' : 'Часы работы не подтверждены'}</span>
      {item.distance_method === 'straight_line' && <p>Путь и время перехода не проверены; уложиться в бюджет не гарантируем.</p>}
      {item.walking_minutes !== null && <p>Пешком: ~{Math.round(item.walking_minutes)} мин{item.total_minutes !== null ? ` · всего ~${Math.ceil(item.total_minutes)} мин` : ''}.</p>}
      {visibleCaveats.map((caveat, i) => <p key={i}><Info size={12} />{caveat}</p>)}
    </div>
    <details className="source-details"><summary><ShieldCheck size={14} />Источники и сведения<ChevronDown size={14} /></summary>
      <div className="source-body">
        <p><strong>Факт из источника:</strong> {poi.description || categoryName(poi.category)}</p>
        {poi.address && <p><strong>Адрес:</strong> {poi.address}</p>}
        <p><strong>Расписание:</strong> {poi.opening_hours_raw || 'нет данных'}</p>
        <dl className="attributes">{Object.entries(ru.attributes).map(([key, label]) =>
          <div key={key}><dt>{label}</dt><dd>{poi.attributes[key] === true ? 'Подтверждено' : poi.attributes[key] === false ? 'Нет' : 'Нет данных'}</dd></div>)}</dl>
        <p>Загружено: {formatDate(poi.collected_at)}. Это дата сбора, не подтверждение заведением.</p>
        <p>Изменение в источнике: {formatDate(poi.source_updated_at)}.</p>
        <p>Координаты: {poi.coordinate_kind === 'node' || poi.coordinate_kind === 'point' ? 'точка объекта' : 'центр объекта; вход может находиться в другом месте'}.</p>
        {detailCaveats.map(caveat => <p key={caveat}>{caveat}</p>)}
        {!!item.evidence_field_ids.length && <p>Поля для объяснения: {item.evidence_field_ids.join(', ')}.</p>}
        <a href={safeUrl(poi.source_url)} target="_blank" rel="noopener noreferrer">Запись OpenStreetMap<ExternalLink size={13} /></a>
      </div>
    </details>
    <div className="place-actions"><button onClick={onSelect}>На карте<MapPin size={14} /></button>
      <a href={safeUrl(item.maps_url)} target="_blank" rel="noopener noreferrer">Открыть в картах<ExternalLink size={14} /></a></div>
  </article>
}
