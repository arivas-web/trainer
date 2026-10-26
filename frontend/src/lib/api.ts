import { API_BASE } from './config'
import { accessToken } from './supabase'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* cuerpo no JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: BodyInit) => request<T>(path, { method: 'POST', body }),
}

// ---- tipos de la API de sincronización (se generarán desde el OpenAPI en la Fase 4) ----

export interface KindStatus {
  pending: number
  running: number
  done: number
  error: number
  items: number
}

export interface SyncStatus {
  run_id: string | null
  finished: boolean
  progress: number
  total_jobs?: number
  finished_jobs?: number
  by_kind?: Record<string, KindStatus>
  errors?: string[]
}

export interface SportRow {
  sport: string
  sub_sport: string | null
  count: number
  km: number
  hours: number
}

export interface Summary {
  activities: {
    total: number
    first: string | null
    last: string | null
    by_sport: SportRow[]
    by_source: Record<string, number>
    with_streams: number
    with_power: number
    with_running_dynamics: number
    with_hr: number
    with_fit: number
  }
  daily: {
    days: number
    first: string | null
    last: string | null
    coverage: Record<string, number>
    arriving: string[]
    missing: string[]
  }
  garmin_kinds: Record<string, { configured: boolean; raw_records: number }>
  jobs: Record<string, number>
  recent_errors: { at: string; kind: string; path: string; http: number | null; error: string }[]
}

export interface ImportResult {
  created: number
  updated: number
  skipped: number
  errors: string[]
}
