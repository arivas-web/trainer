import type { Session } from '@supabase/supabase-js'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { authDisabled, supabase } from '@/lib/supabase'

/** Muestra el login (enlace mágico) hasta que hay sesión de Supabase. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(authDisabled || !supabase)

  useEffect(() => {
    if (authDisabled || !supabase) return
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  if (authDisabled) return <>{children}</>
  if (!supabase) {
    return (
      <Centered>
        <p className="text-ink-soft">
          Falta configurar <code>VITE_SUPABASE_URL</code> y <code>VITE_SUPABASE_ANON_KEY</code>.
        </p>
      </Centered>
    )
  }
  if (!ready) return <Centered>Cargando…</Centered>
  if (!session) return <Login />
  return <>{children}</>
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="grid min-h-dvh place-items-center p-4">{children}</div>
}

function Login() {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!supabase) return
    setState('sending')
    const { error: err } = await supabase.auth.signInWithOtp({
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
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-10" />
          <div>
            <h1 className="text-xl font-semibold">Pulse</h1>
            <p className="text-sm text-ink-soft">Tu laboratorio de rendimiento</p>
          </div>
        </div>
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
