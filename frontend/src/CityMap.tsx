import { useEffect, useState } from 'react'
import { MapContainer, Marker, TileLayer, Tooltip, ZoomControl, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { ArrowUpRight, Crosshair, MapPin, Navigation2, Layers } from 'lucide-react'
import type { Location, Origin, Recommendation } from './types'
import { categoryName } from './i18n'

interface Props {
  origin: Origin | null; landmarks: Location[]; recommendations: Recommendation[];
  selected: string | null; picking: boolean; mobileView: string;
  onPick: (origin: Origin) => void; onSelect: (id: string) => void;
  onPicking: () => void; onLocation: (location: Location) => void;
}
function Controller({ origin, recommendations, selected, picking, onPick, mobileView }: Props) {
  const map = useMap()
  useMapEvents({ click: ({ latlng }) => {
    if (picking) onPick({ latitude: latlng.lat, longitude: latlng.lng, label: 'Точка на карте' })
  } })
  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 100)
    return () => window.clearTimeout(timer)
  }, [map, mobileView])
  useEffect(() => {
    const points: L.LatLngTuple[] = recommendations.map(({ poi }) => [poi.latitude, poi.longitude])
    if (origin) points.push([origin.latitude, origin.longitude])
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [85, 85], maxZoom: 15 })
    else if (points.length === 1) map.setView(points[0], 14)
  }, [map, origin, recommendations])
  useEffect(() => {
    const poi = recommendations.find(item => item.poi.id === selected)?.poi
    if (poi) map.panTo([poi.latitude, poi.longitude], { animate: !matchMedia('(prefers-reduced-motion: reduce)').matches })
  }, [map, selected, recommendations])
  return null
}
const markerIcon = (index: number, active: boolean) => L.divIcon({
  className: 'numbered-marker-wrapper',
  html: `<span class="numbered-marker ${active ? 'active' : ''}">${index + 1}</span>`,
  iconSize: [40, 46], iconAnchor: [20, 42],
})
const originIcon = L.divIcon({
  className: 'origin-marker-wrapper', html: '<span class="origin-marker"><span></span></span>',
  iconSize: [28, 28], iconAnchor: [14, 14],
})
const landmarkIcon = L.divIcon({
  className: 'landmark-marker-wrapper',
  html: '<span class="landmark-marker"></span>', iconSize: [16, 16], iconAnchor: [8, 8],
})
export default function CityMap(props: Props) {
  const [tileError, setTileError] = useState(false)
  const center: L.LatLngTuple = props.landmarks[0]
    ? [props.landmarks[0].latitude, props.landmarks[0].longitude] : [51.128, 71.43]
  const env = (import.meta as unknown as { env: Record<string, string> }).env
  return <section className={`map-panel ${props.picking ? 'picking' : ''}`} data-testid="map-panel" aria-label="Карта Астаны">
    <MapContainer center={center} zoom={13} zoomControl={false} className="city-map">
      <TileLayer
        url={env.VITE_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'}
        attribution={env.VITE_TILE_ATTRIBUTION || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}
        eventHandlers={{ tileerror: () => setTileError(true), tileload: () => setTileError(false) }}
      />
      <ZoomControl position="bottomright" />
      <Controller {...props} />
      {props.origin && <Marker position={[props.origin.latitude, props.origin.longitude]} icon={originIcon}>
        <Tooltip>Отсюда начнём · {props.origin.label}</Tooltip>
      </Marker>}
      {props.recommendations.length ? props.recommendations.map((item, index) =>
        <Marker key={item.poi.id} position={[item.poi.latitude, item.poi.longitude]}
          icon={markerIcon(index, props.selected === item.poi.id)}
          title={`${index + 1}. ${item.poi.name}`} alt={`${index + 1}. ${item.poi.name}`}
          eventHandlers={{ click: () => props.onSelect(item.poi.id) }}>
          <Tooltip direction="top" offset={[0, -40]}>{item.poi.name}<br /><span>{categoryName(item.poi.category)}</span></Tooltip>
        </Marker>) : props.landmarks.map(location =>
        <Marker key={location.id} position={[location.latitude, location.longitude]} icon={landmarkIcon}
          title={`Начать здесь: ${location.name}`} eventHandlers={{ click: () => props.onLocation(location) }}>
          <Tooltip>{location.name} · выбрать отправной точкой</Tooltip>
        </Marker>)}
    </MapContainer>
    <div className="map-top">
      <div className="city-label"><span className="city-dot" /><div><strong>Астана</strong><span>Казахстан · UTC+5</span></div></div>
      <button className={`map-pick-button ${props.picking ? 'is-active' : ''}`} onClick={props.onPicking}>
        <Crosshair size={17} /><span>{props.picking ? 'Отменить выбор' : 'Выбрать точку'}</span>
      </button>
    </div>
    {props.picking && <div className="map-notice"><MapPin size={17} />Нажми на карту — здесь начнётся прогулка</div>}
    {tileError && <div className="tile-error" role="status"><Layers size={15} />Подложка недоступна. Выбор мест в списке работает.</div>}
    {!props.recommendations.length && !props.picking && <div className="map-editorial">
      <span className="eyebrow">ГОРОД БЛИЖЕ, ЧЕМ КАЖЕТСЯ</span>
      <div className="map-editorial-title">Сверни<br />с привычного пути.<ArrowUpRight aria-hidden="true" /></div>
      <p>Немного свободного времени —<br />уже хороший повод выйти.</p>
      <div className="map-editorial-foot"><Navigation2 size={16} />Твой следующий шаг — совсем рядом</div>
    </div>}
    {props.recommendations.length > 0 && <div className="map-legend">
      <span><i className="legend-origin" />Старт</span><span><i className="legend-place" />Подобранные места</span>
      <small>Отдельные варианты, не готовый маршрут</small>
    </div>}
  </section>
}
