import type { DatasetStatus, Location, RecommendRequest, RecommendResponse } from './types'

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    if (response.status === 422) throw new Error('Проверь параметры запроса: координаты, время и длину текста.')
    throw new Error('Не удалось связаться с сервисом. Проверь подключение и попробуй ещё раз.')
  }
  return response.json() as Promise<T>
}
export const getDataset = () => fetchJson<DatasetStatus>('/api/dataset/status')
export const getHealth = () => fetchJson<{ llm_configured: boolean }>('/health')
export const searchLocations = (query: string, signal?: AbortSignal) =>
  fetchJson<{ locations: Location[] }>(`/api/locations/search?q=${encodeURIComponent(query)}&limit=8`, { signal })
export const recommend = (body: RecommendRequest, signal: AbortSignal) =>
  fetchJson<RecommendResponse>('/api/recommend', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal,
  })
