# Pulse — Fase 0: propuesta de arquitectura, esquema y plan (v3)

Estado: **pendiente de OK de Adrián**. No hay código todavía.

## 0. Decisiones confirmadas

| Tema | Decisión |
|---|---|
| Acceso a Garmin | **Garmin Connect Personal API** (clave API personal, creada el 26/10/2026, caduca el 26/10/2027) |
| Reloj | Forerunner 165: FC óptica de muñeca, potencia de carrera de muñeca |
| Objetivo A | Media maratón Vig-Bay, **11/04/2027**, sub-1h45 |
| 70.3 | Sin carrera fijada: el estimador funciona sin fecha y sin cuenta atrás (configurable cuando la haya) |
| Despliegue | **Vercel + Supabase** (web, no local) |
| Umbrales | Con historial (`athlete_thresholds.effective_from`) |
| TRIMP | Factor de hombre (1,92) |
| Histórico inicial | 12 meses |

## 1. Garmin Personal API: qué es y cómo encaja

Es el nuevo nivel gratuito y de autoservicio del Garmin Connect Developer Program (octubre de 2026), pensado para usar **tus propios datos**. Según fuentes secundarias, a falta de verificarlo contra la especificación oficial:

- **Pull, solo lectura.** Nosotros pedimos los datos: **no hacen falta webhooks** y desaparece toda la parte de push/ping de la v2.
- **Canje de token (confirmado por Adrián desde la documentación oficial):**
  `POST https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token`
  con la cabecera `Authorization: ApiKey <clave>`. Pendiente: la forma exacta de la respuesta y la cabecera con la que se envía el token a los endpoints de datos.
- **Autenticación:** la clave personal se canjea por un access token OAuth2 que dura **24 h** y no tiene refresh token. El backend guarda la clave (variable de entorno cifrada en Vercel) y renueva el token cuando caduca.
- **Contenido:** actividades (resumen, búsqueda, detalle y **descarga del FIT original**), sueño, HRV, Body Battery, SpO2, estrés, pasos, peso, Fitness Age y zonas de FC. Hay una especificación OpenAPI oficial (≈ 26 endpoints, todos GET).
- **Límites de rango por petición** (secundario): estrés y pasos ≤ 28 días, sueño ≤ 31 días, resúmenes diarios hasta 1 año. Los rate limits no están publicados → pausa configurable + backoff ante 429/5xx, como pedía la especificación.
- **Campos recortados:** se ha publicado que Garmin elimina de los FIT servidos por API campos no documentados (estimación de VO2max, tiempo de recuperación, performance condition). Si se confirma, el VO2max de Garmin se mostrará como "sin datos" y quedará el VO2max propio estimado desde el VDOT.
- **Caducidad de la clave:** 1 año. Pulse avisará 30 días antes en Ajustes e Insights.

**Lo que probablemente no esté** (se confirma con la especificación y con `make probe`): Training Readiness, Training Status, Race Predictor de Garmin, Endurance/Hill Score, récords de Garmin, material y clima. Sustitutos: readiness propio; predicciones Riegel + VDOT + velocidad crítica; récords calculados desde los streams; zapatillas gestionadas a mano en Pulse con reglas de asignación; temperatura del FIT + Open-Meteo opcional.

**Seguridad:** la clave **nunca** se pega en el chat ni en el repo. Va solo en las variables de entorno de Vercel (`GARMIN_PERSONAL_API_KEY`) y en tu `.env.local` para desarrollo.

## 2. Cambios respecto a la especificación original por usar Vercel + Supabase

| Original | Nuevo | Por qué |
|---|---|---|
| SQLite (WAL) | **Postgres de Supabase** desde el primer día | Vercel no tiene disco persistente. Alembic sigue gestionando las migraciones. |
| FastAPI local | **FastAPI como función Python en Vercel** | Vercel ejecuta FastAPI de forma nativa. Numpy y scipy caben en el bundle. |
| APScheduler | **`pg_cron` + `pg_net` de Supabase**, que llaman a `/api/sync/tick` (protegido con un secreto) | En serverless no hay proceso persistente, y el cron de Vercel Hobby solo se ejecuta 1 vez al día. |
| Sync de 12 meses en una llamada | **Cola de trabajos `sync_jobs`** troceada en rangos de ≤ 28 días; cada tick procesa unos cuantos trozos | Las funciones de Vercel tienen tiempo máximo de ejecución. Es reanudable si algo falla. |
| PIN en `.env` | **Supabase Auth** (magic link a tu email) + RLS + lista blanca con un solo usuario | La app está en internet. |
| FIT en `data/` | **Supabase Storage** (bucket privado) | Mismo motivo. |
| Subida de FIT/zip por la API | FIT sueltos: subida directa del navegador a Storage. Export zip completo: CLI local `make import` | Límite de 4,5 MB por petición en Vercel. |
| SSE | Progreso en `sync_jobs` + Supabase Realtime (o polling) | Serverless no mantiene conexiones largas. |
| "Ningún dato sale salvo hacia Garmin" | Los datos viven en Supabase y Vercel, ambos en la **UE** (Frankfurt) | Lo asumes al elegir alojamiento. |

Fuente alternativa `garminconnect` (no oficial): **descartada como principal**. Desde las IP de Vercel probablemente Garmin la bloquee, y la Personal API la hace innecesaria. Si a la Personal API le faltara algo crítico, podría añadirse como fuente secundaria opcional ejecutada en tu ordenador.

## 3. Arquitectura

```
pulse/
├─ api/index.py              entrypoint de Vercel → backend.app.main:app
├─ backend/app/
│  ├─ sources/               garmin_personal.py (cliente generado desde el OpenAPI oficial), fit_import.py, base.py (GarminSource)
│  ├─ sync/                  cola de trabajos (sync_jobs), workers idempotentes, re-sync de 3 días
│  ├─ models/ analytics/ insights/ api/ core/
│  └─ alembic/
├─ frontend/                 Vite + React 18 + TS + Tailwind (build estático servido por Vercel)
├─ supabase/                 config, políticas RLS, pg_cron (SQL versionado)
├─ scripts/import_export.py  CLI local para el zip completo de Garmin
├─ vercel.json
└─ Makefile                  setup | dev | test | lint | migrate | import
```

**Desarrollo local:** `make dev` levanta Postgres local (Supabase CLI o Docker) + uvicorn + Vite, con la clave en `.env.local`.

## 4. Esquema (Postgres)

Igual que en la v1, con estos cambios (implementado en la Fase 1): **sin `user_id`**: todas las tablas tienen RLS activado sin políticas, así que solo el backend (conexión directa) accede a los datos y la clave pública de Supabase solo sirve para el login; `garmin_token` (access token cacheado + caducidad; la clave vive en env) y `sync_jobs` (cola + progreso).

```
activities           id, user_id, source, external_id, UNIQUE(source, external_id),
                     start_time_utc, start_time_local, tz_offset_min, sport, sub_sport, name, device,
                     distance_m, duration_s, moving_s, elev_gain_m, elev_loss_m, avg/max_hr,
                     avg/max_speed, avg_cadence, avg/max/normalized_power, aerobic_te, anaerobic_te,
                     garmin_training_load, vo2max, calories, avg_temp_c, weather_json, gear_id,
                     has_streams, has_power, has_running_dynamics,
                     is_race, is_trail, excluded_from_analytics, rpe, notes   ← manuales, la sync no los pisa
activity_streams     activity_id, n_samples, channels, data bytea (float32 por canal + zlib)
laps · swim_lengths · best_efforts · personal_records
computed_activity_metrics (inputs_hash, algo_version, load_method, …)
daily_metrics · daily_load (ctl, atl, tsb, acwr, ramp, monotony, strain)
gear (manual) · athlete_thresholds (effective_from) · app_settings
races · goals · insights · ai_reports · planned_workouts (fase final)
raw_documents        kind, key, payload jsonb (o comprimido en Storage si es grande)
garmin_token         access_token (cifrado), expires_at, key_expires_at
sync_jobs            id, kind (backfill|pull|recompute), range, status, progress, error
sync_state · sync_log
```

## 5. Plan de fases (ajustado)

- **F1 — Esqueleto y sincronización** 🛑: monorepo, Vercel + Supabase, migraciones, auth, cliente de la Personal API generado desde su OpenAPI, `make probe`, sync incremental + backfill de 12 meses troceado, importación FIT y resumen de lo recibido (n.º de actividades por deporte, rango de fechas, qué tipos de datos llegan y cuáles no). Tests con payloads de ejemplo.
- **F2 — Analítica** 🛑 · **F3 — Diseño** 🛑 · **F4 — Vistas principales** 🛑 · **F5 — Secundarias, PWA, ⌘K** 🛑 · **F6 — IA y pulido**. Sin cambios respecto a tu especificación, salvo que el acceso móvil ya no es "misma wifi + PIN" sino la URL de Vercel con login.

Decisiones defendibles que ya tomo (configurables): GAP con Minetti (2002); ACWR por EWMA; zonas de FC Friel por % de LTHR; TRIMP de Banister con factor 1,92; velocidad crítica por ajuste lineal distancia–tiempo con esfuerzos de 3 a 20 min.

## 6. Referencia visual (imagen que mandó Adrián)

La referencia es un glassmorphism **claro**, distinto del apartado 8 de la especificación (oscuro `#07070C` con auroras). Rasgos que se toman de ella:

- Fondo degradado celeste (de `#BFE3F7` a `#E6F3FB`) con manchas de luz grandes y suaves, en lugar de las auroras oscuras.
- Tarjetas blancas translúcidas (`rgba(255,255,255,0.45–0.6)` + `blur(24px)`), borde blanco de 1 px, sombra azulada muy difusa y radio de unos 24 px.
- Navegación doble: un rail de iconos estrecho + un panel de navegación con subsecciones en árbol. En el móvil se convierte en una tab bar inferior.
- Etiquetas de sección en mayúsculas pequeñas con tracking amplio y gris azulado, y enlaces "Ver todo >" a la derecha.
- KPI grande y oscuro con sparkline de color semántico y variación % en verde o rojo.
- Pastillas con borde de color para los estados (Baja/Media → Z1–Z5, readiness, etc.).
- Azul primario vivo (`#1A7CF5`) para los acentos y el elemento activo.

Propuesta: **tema claro por defecto según la referencia** y tema oscuro "aurora" de la especificación como alternativa (con conmutador y respetando `prefers-color-scheme`). Ambos temas comparten tokens, así que el coste es bajo. Los colores por deporte y por zona se ajustan para mantener contraste AA sobre fondo claro.
