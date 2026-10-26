/** URL de la API. En Vercel la web y la API son proyectos distintos: VITE_API_URL apunta al
 *  proyecto backend. En local queda vacía y Vite redirige /api al backend (vite.config.ts). */
export const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(
  /\/+$/,
  '',
)

export const API_BASE_MISSING =
  API_BASE === '' && !['localhost', '127.0.0.1'].includes(window.location.hostname)
