import { createClient, type SupabaseClient } from '@supabase/supabase-js'

import { API_BASE } from './config'

export interface PublicConfig {
  supabase_url: string | null
  supabase_anon_key: string | null
  auth_disabled: boolean
}

let client: SupabaseClient | null = null

/** El backend sirve la URL y la clave pública de Supabase en /api/config, así que no hacen
 *  falta variables VITE_* en el build (ni redeploy al cambiarlas). */
export async function loadConfig(): Promise<PublicConfig> {
  const res = await fetch(`${API_BASE}/api/config`)
  if (!res.ok) throw new Error(`No se pudo leer /api/config (HTTP ${res.status})`)
  const cfg = (await res.json()) as PublicConfig
  if (cfg.supabase_url && cfg.supabase_anon_key && !client) {
    client = createClient(cfg.supabase_url, cfg.supabase_anon_key, {
      auth: { persistSession: true, detectSessionInUrl: true },
    })
  }
  return cfg
}

export function supabase(): SupabaseClient | null {
  return client
}

export async function accessToken(): Promise<string | null> {
  if (!client) return null
  const { data } = await client.auth.getSession()
  return data.session?.access_token ?? null
}
