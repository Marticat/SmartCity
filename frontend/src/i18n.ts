/** Copy is separated so additional locales can be added without a misleading language switch. */
export const ru = {
  tagline: 'Хорошая прогулка начинается рядом',
  categories: {
    cafe: 'Кафе', museum: 'Музей', park: 'Парк', playground: 'Детская площадка',
    attraction: 'Достопримечательность', gallery: 'Галерея', viewpoint: 'Смотровая площадка',
    artwork: 'Искусство', monument: 'Памятник', memorial: 'Мемориал',
    garden: 'Сад', restaurant: 'Ресторан', library: 'Библиотека', theatre: 'Театр',
  } as Record<string, string>,
  attributes: {
    indoor: 'В помещении', wifi: 'Wi-Fi', sockets: 'Розетки', wheelchair: 'Доступность',
    free: 'Бесплатно',
  } as Record<string, string>,
}
export const categoryName = (category: string) => ru.categories[category] || 'Место в городе'
export const formatDate = (value: string | null) => value && Number.isFinite(new Date(value).getTime())
  ? new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Almaty' }).format(new Date(value))
  : 'дата неизвестна'
const evidenceLabels: Record<string, string> = {
  name: 'название', category: 'категория', description: 'описание', address: 'адрес',
  latitude: 'местоположение', longitude: 'местоположение', opening_hours_raw: 'расписание',
  'attributes.indoor': 'нахождение в помещении', 'attributes.wifi': 'Wi-Fi',
  'attributes.sockets': 'розетки', 'attributes.wheelchair': 'доступность объекта',
  'attributes.free': 'плата за вход', website: 'сайт объекта',
  'attributes.interactive': 'интерактивные экспонаты', 'attributes.architecture': 'архитектура',
  'attributes.history': 'история', 'attributes.science': 'научная тематика',
  'attributes.family_friendly': 'семейное посещение', 'attributes.child_friendly': 'занятия для детей',
}
export const evidenceName = (field: string) => evidenceLabels[field] || 'дополнительные сведения источника'
export const safeUrl = (value: string | null | undefined) => {
  try { const url = new URL(value || ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined }
  catch { return undefined }
}
