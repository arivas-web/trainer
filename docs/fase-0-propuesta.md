# Pulse — Fase 0: propuesta de arquitectura, esquema y plan (v2)

Estado: **pendiente de OK de Adrián**. No hay código todavía.

## 0. Decisiones confirmadas

| Tema | Decisión |
|---|---|
| Acceso a Garmin | **Garmin Connect Developer Program** (Health API + Activity API oficiales, push/ping a webhooks) |
| Reloj | Forerunner 165: FC óptica de muñeca, potencia de carrera de muñeca |
| Objetivo A | Media maratón Vig-Bay, **11/04/2027**, sub-1h45 |
| 70.3 | Sin carrera fijada: el estimador funciona sin fecha y sin cuenta atrás (configurable cuando la haya) |
| Despliegue | **Vercel + Supabase** (web, no local) |
| Umbrales | Con historial (`athlete_thresholds.effective_from`) |
| TRIMP | Factor de hombre (1,92) |
| Histórico inicial | 12 meses |

## 1. Lo que cambia respecto a la especificación original

La especificación decía "local y privado, SQLite, PIN en `.env`". Con Vercel + Supabase:

| Original | Nuevo | Por qué |
|---|---|---|
| SQLite (WAL) | **Postgres de Supabase** desde el primer día | Vercel no tiene disco persistente. Alembic sigue gestionando las migraciones. |
| FastAPI en tu máquina | **FastAPI como función Python en Vercel** (`api/index.py`, ASGI) | Vercel ejecuta FastAPI de forma nativa. La analítica (numpy/scipy) cabe en el límite de 250 MB del bundle. |
| APScheduler | **`pg_cron` + `pg_net` de Supabase**, que llaman a un endpoint protegido de Vercel | El scheduler en proceso no sobrevive en serverless. Vercel Cron en el plan Hobby solo se ejecuta 1 vez al día. |
| PIN en `.env` | **Supabase Auth** (magic link a tu email) + RLS en todas las tablas + lista blanca con un solo usuario | Ahora la app está en internet y un PIN no basta. |
| FIT originales en `data/` | **Supabase Storage** (bucket privado) | Mismo motivo. |
| Subida de FIT/zip por la API | Subida **directa del navegador a Storage** con URL firmada, y después procesado | Vercel limita el cuerpo de las peticiones a 4,5 MB. Un export completo de Garmin (que pesa GB) se importa con un CLI local que escribe en Supabase. |
| SSE para el progreso | Progreso en la tabla `sync_jobs` + **Supabase Realtime** (o polling) | Las funciones serverless no mantienen conexiones largas. |
| "Ningún dato sale salvo hacia Garmin" | Los datos viven en Supabase (proyecto en región **UE**, Frankfurt) y se procesan en Vercel (región `fra1`) | Lo asumes al elegir alojamiento. Te lo dejo explícito. |

## 2. Garmin Developer Program: realidad y huecos

**Cómo funciona.** Garmin no se consulta: Garmin **avisa**. Tras el OAuth con tu cuenta, cada vez que el reloj sincroniza, Garmin hace un POST a nuestros webhooks.

- Usaré el modo **ping/pull** siempre que el portal lo permita: llega un aviso con un `callbackURL`, nosotros pedimos los datos con nuestro token y guardamos la respuesta cruda. Esto evita el límite de 4,5 MB de Vercel con `activityDetails` grandes y verifica que la petición es legítima. Hasta donde sé, Garmin no firma los webhooks.
- **Backfill de 12 meses:** la API de backfill es asíncrona. Se pide un rango y los datos llegan después por los mismos webhooks. Hay límites por rango y por día, así que lo trocearé y lo encolaré.
- Obligatorio en el programa: atender `deregistrations` y `userPermissionsChange`.

**Lo que la API oficial NO da (hasta donde sé; lo confirmo contra tu portal).** Estos datos se mostrarán como "sin datos" o los calcularé yo:

| Dato de la especificación | Situación con la API oficial | Alternativa |
|---|---|---|
| Training Readiness, Training Status | No disponible. Además, el FR165 probablemente no lo tiene. | Readiness propio (apartado 5.5), que era el plan de todas formas |
| Race Predictor de Garmin | No disponible | Riegel + VDOT + velocidad crítica propios |
| Endurance Score, Hill Score | No disponible | Se omite |
| Récords de Garmin | No disponible | Récords calculados desde los streams (mejor de todas formas) |
| Material (zapatillas) | No disponible | Gestión manual de zapatillas en Pulse + asignación por reglas (por ejemplo, "trail → zapatilla X") |
| Clima de la actividad | No disponible | Temperatura del sensor del FIT si existe; opcional: Open-Meteo histórico por lat/lon y hora |
| HRV, sueño, estrés, Body Battery, FC en reposo, VO2max, SpO2, respiración, composición corporal | **Sí** (Health API: dailies, sleeps, hrv, stressDetails, userMetrics, pulseOx, respiration, bodyComps) | — |
| Streams (FC, ritmo, GPS, cadencia, potencia, altitud) | **Sí** (activityDetails y/o FIT de Activity Files) | Preferiré el FIT original, que es más rico (dinámica de carrera), con activityDetails de respaldo |

**FR165:** la dinámica de carrera disponible solo desde la muñeca (cadencia y zancada seguro; tiempo de contacto y oscilación vertical, dudoso) y la potencia de muñeca se confirmarán con tus primeros FIT. Todo lo que falte se mostrará como "sin datos".

**Importación FIT/GPX/TCX/zip:** sigue disponible como respaldo.

## 3. Arquitectura

```
pulse/
├─ api/index.py              entrypoint de Vercel → backend.app.main:app
├─ backend/app/
│  ├─ sources/               garmin_official.py (OAuth, webhooks, backfill), fit_import.py, base.py (GarminSource)
│  ├─ sync/                  cola de trabajos (sync_jobs), workers idempotentes, re-sync de 3 días
│  ├─ models/ analytics/ insights/ api/ core/
│  └─ alembic/
├─ frontend/                 Vite + React 18 + TS + Tailwind (build estático servido por Vercel)
├─ supabase/                 config, políticas RLS, pg_cron (SQL versionado)
├─ scripts/import_export.py  CLI local para el zip completo de Garmin
├─ vercel.json
└─ Makefile                  setup | dev | test | lint | migrate | import
```

**Desarrollo local:** `make dev` levanta Postgres local (Supabase CLI o Docker) + uvicorn + Vite. Los webhooks de Garmin en local se prueban con cloudflared (lo documento), pero lo normal será probarlos directamente en un Preview Deploy de Vercel.

## 4. Esquema (Postgres)

Igual que en la v1, con estos cambios: `user_id` en las tablas de datos (por la RLS, aunque seas un solo usuario), `garmin_oauth` (tokens cifrados y garmin_user_id), `sync_jobs` (cola + progreso) y `webhook_events` (registro idempotente de cada aviso recibido).

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
garmin_oauth         user_id, garmin_user_id, tokens (cifrados con una clave en env), scopes, connected_at
webhook_events       id, type, received_at, payload, status, error  (idempotencia + depuración)
sync_jobs            id, kind (backfill|pull|recompute), range, status, progress, error
sync_state · sync_log
```

## 5. Plan de fases (ajustado)

- **F1 — Esqueleto y sincronización** 🛑: monorepo, Vercel + Supabase, migraciones, auth, OAuth de Garmin, webhooks, backfill de 12 meses troceado, importación FIT y resumen de lo recibido (n.º de actividades por deporte, rango de fechas, qué tipos de datos llegan y cuáles no). Tests con payloads de ejemplo.
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
