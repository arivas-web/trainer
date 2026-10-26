import type { Session } from '@supabase/supabase-js'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { API_BASE, API_BASE_MISSING } from '@/lib/config'
import { loadConfig, supabase, type PublicConfig } from '@/lib/supabase'

interface Health {
  ok: boolean
  checks: Record<string, boolean>
  required: string[]
  db_error: string | null
}

const CHECK_HELP: Record<string, string> = {
  database:
    'Conecta Supabase al proyecto (Vercel → Storage → Supabase) o define DATABASE_URL. Después, Redeploy.',
  garmin_key: 'Añade GARMIN_PERSONAL_API_KEY en Vercel → Settings → Environment Variables.',
  supabase_url: 'Conecta Supabase desde Vercel → Storage (crea SUPABASE_URL).',
  supabase_anon_key: 'Conecta Supabase desde Vercel → Storage (crea la clave anon/publishable).',
  allowed_email: 'Añade ALLOWED_EMAIL con tu email.',
  storage: 'Falta SUPABASE_SERVICE_ROLE_KEY para guardar los FIT originales.',
  cron_secret: 'Opcional: CRON_SECRET activa la sincronización diaria automática.',
}

type State =
  | { kind: 'loading' }
  | { kind: 'setup'; health: Health | null; error?: string }
  | { kind: 'ready'; config: PublicConfig }

/** Comprueba la puesta a punto y muestra el login (enlace mágico) hasta que hay sesión. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [session, setSession] = useState<Session | null>(null)

  useEffect(() => {
    let unsub: (() => void) | undefined
    void (async () => {
      if (API_BASE_MISSING) {
        setState({
          kind: 'setup',
          health: null,
          error:
            'Falta VITE_API_URL en el proyecto frontend de Vercel (la URL del proyecto backend). Añádela y haz Redeploy.',
        })
        return
      }
      try {
        const health = (await (await fetch(`${API_BASE}/api/health`)).json()) as Health
        if (!health.ok) {
          setState({ kind: 'setup', health })
          return
        }
        const config = await loadConfig()
        const sb = supabase()
        if (sb) {
          const { data } = await sb.auth.getSession()
          setSession(data.session)
          const { data: sub } = sb.auth.onAuthStateChange((_e, s) => setSession(s))
          unsub = () => sub.subscription.unsubscribe()
        }
        setState({ kind: 'ready', config })
      } catch (err) {
        setState({ kind: 'setup', health: null, error: (err as Error).message })
      }
    })()
    return () => unsub?.()
  }, [])

  if (state.kind === 'loading') return <Centered>Cargando…</Centered>
  if (state.kind === 'setup') return <Setup health={state.health} error={state.error} />
  if (state.config.auth_disabled) return <>{children}</>
  if (!session) return <Login />
  return <>{children}</>
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="grid min-h-dvh place-items-center p-4">{children}</div>
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <img src="/favicon.svg" alt="" className="size-10" />
      <div>
        <h1 className="text-xl font-semibold">Pulse</h1>
        <p className="text-sm text-ink-soft">Tu laboratorio de rendimiento</p>
      </div>
    </div>
  )
}

function Setup({ health, error }: { health: Health | null; error?: string }) {
  return (
    <Centered>
      <div className="glass w-full max-w-md space-y-4 p-6">
        <Brand />
        <p className="label">Puesta a punto</p>
        {error && <p className="text-sm text-bad">{error}</p>}
        {health && (
          <ul className="space-y-2 text-sm">
            {Object.entries(health.checks).map(([k, ok]) => (
              <li key={k} className="flex gap-2">
                <span
                  className={
                    ok ? 'text-ok' : health.required.includes(k) ? 'text-bad' : 'text-warn'
                  }
                >
                  {ok ? '✓' : health.required.includes(k) ? '✗' : '○'}
                </span>
                <span>
                  <span className="font-medium">{k}</span>
                  {!ok && <span className="block text-ink-soft">{CHECK_HELP[k]}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
        {health?.db_error && (
          <p className="break-words rounded-2xl bg-white/70 p-3 text-xs text-ink-soft">
            {health.db_error}
          </p>
        )}
        <button
          onClick={() => window.location.reload()}
          className="w-full rounded-full bg-accent px-4 py-3 font-medium text-white"
        >
          Volver a comprobar
        </button>
      </div>
    </Centered>
  )
}

function Login() {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const sb = supabase()
    if (!sb) return
    setState('sending')
    const { error: err } = await sb.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin, shouldCreateUser: false },
    })
    if (err) {
      setError(err.message)
      setState('error')
    } else {
      setState('sent')
    }
  }

  return (
    <Centered>
      <form onSubmit={submit} className="glass w-full max-w-sm space-y-4 p-6">
        <Brand />
        {state === 'sent' ? (
          <p className="text-sm">Te he enviado un enlace a {email}. Ábrelo en este dispositivo.</p>
        ) : (
          <>
            <label className="block">
              <span className="label">Email</span>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-2xl border border-white bg-white/70 px-4 py-3 outline-none focus:ring-2 focus:ring-accent"
              />
            </label>
            <button
              disabled={state === 'sending'}
              className="w-full rounded-full bg-accent px-4 py-3 font-medium text-white disabled:opacity-60"
            >
              {state === 'sending' ? 'Enviando…' : 'Enviarme un enlace'}
            </button>
            {error && <p className="text-sm text-bad">{error}</p>}
          </>
        )}
      </form>
    </Centered>
  )
}
