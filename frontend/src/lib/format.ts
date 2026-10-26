import { format, parseISO } from 'date-fns'
import { es } from 'date-fns/locale'

export const NO_DATA = 'sin datos'

/** Ritmo en m:ss /km a partir de una velocidad en m/s. */
export function pace(speedMs: number | null | undefined): string {
  if (!speedMs || speedMs <= 0) return NO_DATA
  const secPerKm = Math.round(1000 / speedMs)
  const m = Math.floor(secPerKm / 60)
  const s = secPerKm % 60
  return `${m}:${String(s).padStart(2, '0')} /km`
}

/** Duración en h:mm:ss (o m:ss si es menos de una hora). */
export function duration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return NO_DATA
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

export function day(iso: string | null | undefined): string {
  if (!iso) return NO_DATA
  return format(parseISO(iso), 'd MMM yyyy', { locale: es })
}

export function number(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return NO_DATA
  return n.toLocaleString('es-ES', { maximumFractionDigits: digits })
}
