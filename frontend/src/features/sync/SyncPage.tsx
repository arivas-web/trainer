import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type ChangeEvent } from 'react'

import { api, type ImportResult, type Summary, type SyncStatus } from '@/lib/api'
import { day, number } from '@/lib/format'
import { supabase } from '@/lib/supabase'

/** Pantalla provisional de la Fase 1: sincronizar, ver progreso y revisar qué ha llegado. */
export function SyncPage() {
  const qc = useQueryClient()
  const status = useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.get<SyncStatus>('/api/sync/status'),
    refetchInterval: (q) => (q.state.data && !q.state.data.finished ? 2000 : false),
  })
  const summary = useQuery({
    queryKey: ['sync-summary'],
    queryFn: () => api.get<Summary>('/api/sync/summary'),
  })
  const start = useMutation({
    mutationFn: () => api.post<{ run_id: string; status: SyncStatus }>('/api/sync'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['sync-status'] }),
  })

  // Mientras haya trabajo pendiente, la propia página empuja la cola (además de pg_cron).
  const running = status.data && !status.data.finished
  const pushing = useRef(false)
  useEffect(() => {
    if (!running || pushing.current) return
    pushing.current = true
    void api
      .post('/api/sync/continue')
      .catch(() => undefined)
      .finally(() => {
        pushing.current = false
        void qc.invalidateQueries({ queryKey: ['sync-status'] })
        void qc.invalidateQueries({ queryKey: ['sync-summary'] })
      })
  }, [running, status.dataUpdatedAt, qc])

  const pct = Math.round((status.data?.progress ?? 1) * 100)

  return (
    <main className="mx-auto max-w-5xl space-y-5 px-4 py-6 pb-24">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-9" />
          <h1 className="text-2xl font-semibold">Sincronización</h1>
        </div>
        {supabase() && (
          <button onClick={() => void supabase()?.auth.signOut()} className="text-sm text-ink-soft">
            Salir
          </button>
        )}
      </header>

      <section className="glass space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="label">Garmin Connect · Personal API</p>
            <p className="text-sm text-ink-soft">
              {running
                ? `Sincronizando… ${status.data?.finished_jobs ?? 0}/${status.data?.total_jobs ?? 0} trabajos`
                : 'Al día'}
            </p>
          </div>
          <button
            onClick={() => start.mutate()}
            disabled={start.isPending || !!running}
            className="rounded-full bg-accent px-5 py-2.5 font-medium text-white disabled:opacity-50"
          >
            {start.isPending ? 'Iniciando…' : 'Sincronizar'}
          </button>
        </div>
        <div
          className="h-2 overflow-hidden rounded-full bg-white/70"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
        </div>
        {start.error && <p className="text-sm text-bad">{start.error.message}</p>}
        {status.data?.errors?.map((e) => (
          <p key={e} className="text-sm text-warn">
            ⚠ {e}
          </p>
        ))}
      </section>

      <GarminCheck />
      {summary.data && <SummaryView s={summary.data} />}
      <ImportCard onDone={() => void qc.invalidateQueries({ queryKey: ['sync-summary'] })} />
    </main>
  )
}

function SummaryView({ s }: { s: Summary }) {
  const a = s.activities
  const d = s.daily
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <section className="glass space-y-3 p-5">
        <p className="label">Actividades</p>
        <p className="num text-5xl font-light">{a.total}</p>
        <p className="text-sm text-ink-soft">
          {day(a.first)} → {day(a.last)}
        </p>
        <table className="num w-full text-sm">
          <tbody>
            {a.by_sport.map((r) => (
              <tr key={`${r.sport}/${r.sub_sport}`} className="border-t border-white/70">
                <td className="py-1.5">
                  {r.sport}
                  {r.sub_sport && r.sub_sport !== 'generic' ? ` · ${r.sub_sport}` : ''}
                </td>
                <td className="text-right">{r.count}</td>
                <td className="text-right text-ink-soft">{number(r.km, 1)} km</td>
                <td className="text-right text-ink-soft">{number(r.hours, 1)} h</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-ink-soft">
          Con FC {a.with_hr} · con potencia {a.with_power} · con dinámica de carrera{' '}
          {a.with_running_dynamics} · con FIT original {a.with_fit}
        </p>
      </section>

      <section className="glass space-y-3 p-5">
        <p className="label">Métricas diarias</p>
        <p className="num text-5xl font-light">{d.days}</p>
        <p className="text-sm text-ink-soft">
          días · {day(d.first)} → {day(d.last)}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(d.coverage).map(([k, v]) => (
            <span
              key={k}
              className={`rounded-full border px-2.5 py-0.5 text-xs ${
                v > 0 ? 'border-ok/40 text-ok' : 'border-ink-soft/30 text-ink-soft'
              }`}
              title={`${v}/${d.days} días`}
            >
              {v > 0 ? '✓' : '—'} {k}
            </span>
          ))}
          {d.days === 0 && <p className="text-sm text-ink-soft">Aún no ha llegado ninguna.</p>}
        </div>
      </section>

      <section className="glass space-y-2 p-5 md:col-span-2">
        <p className="label">Tipos de datos de Garmin</p>
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          {Object.entries(s.garmin_kinds).map(([k, v]) => (
            <li key={k} className="flex justify-between gap-2">
              <span>{k}</span>
              <span className={v.configured ? 'text-ok' : 'text-ink-soft'}>
                {v.configured ? `${v.raw_records} registros` : 'pendiente de mapear'}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function ImportCard({ onDone }: { onDone: () => void }) {
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onFiles(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    setBusy(true)
    setError(null)
    const total: ImportResult = { created: 0, updated: 0, skipped: 0, errors: [] }
    for (const f of files) {
      const fd = new FormData()
      fd.append('file', f)
      try {
        const r = await api.post<ImportResult>('/api/import', fd)
        total.created += r.created
        total.updated += r.updated
        total.skipped += r.skipped
        total.errors.push(...r.errors)
      } catch (err) {
        total.errors.push(`${f.name}: ${(err as Error).message}`)
      }
    }
    setResult(total)
    setBusy(false)
    onDone()
    e.target.value = ''
  }

  return (
    <section className="glass space-y-3 p-5">
      <p className="label">Importar archivos</p>
      <p className="text-sm text-ink-soft">
        FIT, GPX o TCX sueltos (hasta 4 MB cada uno). El export completo de Garmin se importa con{' '}
        <code>make import</code>.
      </p>
      <input
        type="file"
        multiple
        accept=".fit,.gpx,.tcx,.zip"
        onChange={(e) => void onFiles(e)}
        disabled={busy}
        className="text-sm"
      />
      {result && (
        <p className="text-sm">
          {result.created} nuevas · {result.updated} actualizadas · {result.skipped} omitidas
          {result.errors.length > 0 && ` · ${result.errors.length} errores`}
        </p>
      )}
      {error && <p className="text-sm text-bad">{error}</p>}
    </section>
  )
}

interface GarminCheckResult {
  ok: boolean
  step?: string
  error?: string
  http_status?: number
  response_shape?: unknown
  token_expires_at?: string
}

/** Comprueba la clave API personal desde la web y muestra la forma de la respuesta. */
function GarminCheck() {
  const check = useMutation({
    mutationFn: () => api.get<GarminCheckResult>('/api/garmin/check'),
  })
  const r = check.data
  return (
    <section className="glass space-y-3 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="label">Conexión con Garmin</p>
          <p className="text-sm text-ink-soft">
            Canjea tu clave API personal por un token de 24 h.
          </p>
        </div>
        <button
          onClick={() => check.mutate()}
          disabled={check.isPending}
          className="rounded-full border border-accent px-5 py-2.5 font-medium text-accent disabled:opacity-50"
        >
          {check.isPending ? 'Comprobando…' : 'Comprobar conexión'}
        </button>
      </div>
      {check.error && <p className="text-sm text-bad">{check.error.message}</p>}
      {r && (
        <div className="space-y-2 text-sm">
          <p className={r.ok ? 'text-ok' : 'text-bad'}>
            {r.ok
              ? `✓ Conectado. El token caduca el ${day(r.token_expires_at)}.`
              : `✗ ${r.error ?? 'Error'}${r.http_status ? ` (HTTP ${r.http_status})` : ''}`}
          </p>
          {r.response_shape !== undefined && (
            <>
              <p className="text-ink-soft">
                Forma de la respuesta (sin valores, se puede compartir):
              </p>
              <pre className="overflow-x-auto rounded-2xl bg-white/70 p-3 text-xs">
                {JSON.stringify(r.response_shape, null, 2)}
              </pre>
            </>
          )}
        </div>
      )}
    </section>
  )
}
