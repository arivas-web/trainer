# Pulse — Fase 0: propuesta de esquema y plan

Estado: **pendiente de OK de Adrián**. No hay código todavía.

## 1. Cosas de la especificación que chocan con la realidad (octubre de 2026)

| Punto de la especificación | Realidad | Propuesta |
|---|---|---|
| Tokens con `garth` en `~/.garminconnect` | `garth` está **deprecado**: Garmin cambió el flujo de autenticación y los logins nuevos con garth ya no funcionan. `garminconnect` ≥ 0.3.0 ya no lo usa: hace login por SSO móvil (OAuth Bearer con refresh automático) y guarda los tokens en `~/.garminconnect/garmin_tokens.json` (modo 0600). Última versión: 0.3.20 (23/10/2026). Python ≥ 3.12. | Fijar `garminconnect>=0.3.20,<0.4`. El MFA se resuelve por consola con `prompt_mfa`, y también por la UI con `return_on_mfa=True` + `resume_login()`. Nunca por debajo de 0.3.5 (CVE sobre los permisos del archivo de tokens). |
| Modo B: API oficial (Developer Program) | Es un programa para **empresas**: exige solicitud y aprobación y, en la práctica, no se concede para uso personal. Hay noticias de septiembre de 2026 de que Garmin ha congelado las altas nuevas. | Lo dejo como adaptador "stub" detrás de `GarminSource` (interfaz y mapeo documentados), pero no lo construyo entero salvo que ya tengas credenciales aprobadas. |
| Nombres de endpoints | Los de la lista existen en versiones recientes, pero los nombres y las formas de respuesta cambian entre versiones. | En la Fase 1 hago un script `make probe` que llama a cada método, guarda la respuesta cruda (anonimizada) y genera una tabla de lo que existe para tu cuenta y tu reloj. El mapeo se escribe contra esas respuestas, no de memoria. |
| Desarrollo con tus datos | Trabajo en un contenedor en la nube, **no en tu máquina**. No debo recibir tus credenciales, y Garmin suele bloquear las IP de centros de datos. | El login y la sincronización real los ejecutas tú en local (`make sync`). Yo desarrollo y testeo contra fixtures. Para el checkpoint de la Fase 1, me pegas la salida del resumen de `make sync` y, si quieres, el `make probe --anonymize` para afinar el mapeo. |

## 2. Esquema de base de datos propuesto

Cambios respecto a la especificación, con una línea de justificación cada uno:

1. **`raw_documents` aparte** en lugar de `raw_json` en cada fila. Las respuestas crudas comprimidas (zlib) por `(kind, key)` permiten re-mapear sin volver a descargar y mantienen ligeras las tablas calientes.
2. **Umbrales con historial (`athlete_thresholds`)**: tu LTHR, ritmo umbral, FC máx, CSS y FTP cambian con el tiempo. Calcular un rodaje de hace 10 meses con el LTHR de hoy distorsiona el TSS y el CTL. Cada actividad usa los umbrales vigentes en su fecha. *(Decisión tuya: ver las preguntas.)*
3. **`best_efforts` como tabla** y no como JSON: el ranking histórico y el de 90 días se resuelven con un `ORDER BY` indexado.
4. **`swim_lengths` separado de `laps`**: un largo no es un lap. SWOLF y brazadas viven por largo.
5. **Streams**: una fila por actividad, un BLOB por canal (float32 → zlib). Es portable a Postgres (`bytea`) sin Parquet ni pyarrow, y solo se carga en el detalle.
6. **Invalidación**: `computed_activity_metrics.inputs_hash` = hash de (umbrales vigentes + zonas + método de carga + versión del algoritmo). Si cambia, se recalcula.
7. **Overrides manuales** (`is_race`, `is_trail`, `excluded_from_analytics`, `rpe`, `notes`) en columnas propias que la sincronización **nunca** pisa.

```
activities
  id PK, source, external_id, UNIQUE(source, external_id)
  start_time_utc, start_time_local, tz_offset_min
  sport, sub_sport, name, device
  distance_m, duration_s, moving_s, elev_gain_m, elev_loss_m
  avg_hr, max_hr, avg_speed, max_speed, avg_cadence
  avg_power, max_power, normalized_power
  aerobic_te, anaerobic_te, garmin_training_load, vo2max, calories
  avg_temp_c, weather_json, gear_id FK
  has_streams, has_power, has_running_dynamics
  is_race, is_trail (auto + override), excluded_from_analytics, rpe, notes
  INDEX(start_time_utc), INDEX(sport, start_time_utc)

activity_streams
  activity_id PK/FK, n_samples, channels (lista), data (BLOB por canal: time, distance,
  lat, lon, altitude, hr, speed, cadence, power, temperature, gct, vo, stride_length,
  vertical_ratio), schema_version

laps          activity_id, idx, start_offset_s, duration_s, distance_m, avg_speed, avg_hr,
              max_hr, avg_cadence, avg_power, elev_gain_m, elev_loss_m, intensity (active|rest)
swim_lengths  activity_id, lap_idx, idx, duration_s, stroke_type, strokes, swolf, pool_length_m

computed_activity_metrics
  activity_id PK, inputs_hash, algo_version, computed_at
  load_value, load_method (power_tss|rtss|hrtss|trimp|garmin)
  trimp, hrtss, rtss, tss_power, intensity_factor
  gap_avg_speed, efficiency_factor, decoupling_pct, hr_drift_pct
  pace_at_hr_json ({140: s/km, 150: …}), zone_time_json (hr/pace/power, 5 y 3 zonas)
  vam_m_h, walk_pct (trail)

best_efforts   activity_id, sport, kind (distance|duration), target (m o s), value (s o m),
               start_offset_s, date — INDEX(sport, kind, target, value)
personal_records  sport, kind, target, value, activity_id, date, source (garmin|computed)

daily_metrics  date PK, resting_hr, hrv_night_avg, hrv_weekly_avg, hrv_status,
               sleep_total_s, sleep_deep_s, sleep_light_s, sleep_rem_s, sleep_awake_s,
               sleep_score, sleep_start_local, sleep_end_local,
               body_battery_max/min/charged/drained, stress_avg, steps, active_kcal,
               readiness_score, readiness_factors_json, vo2max_run, vo2max_bike,
               training_status, acute_load, chronic_load, respiration_avg, spo2_avg,
               weight_kg, body_fat_pct, fetched_at
daily_load     date PK, load_total, load_by_sport_json, ctl, atl, tsb, acwr,
               ramp_rate_7d, monotony_7d, strain_7d, inputs_hash

gear           id PK, external_id, name, type (shoes|bike|other), total_km, limit_km (700),
               retired, first_used, last_used
athlete_thresholds  id, effective_from, hr_max, hr_rest, lthr, threshold_pace_s_km,
                    css_s_100m, ftp_w, weight_kg, source (manual|auto_estimated|garmin)
app_settings   key PK, value_json (zonas, métodos de carga, constantes CTL/ATL, pesos de
               readiness, Riegel, objetivos de sueño, IA on/off, intervalos de sync…)
races          id, name, date, distance_m, format (run|tri_70_3|trail…), target_time_s,
               priority (A|B|C), result_activity_id
goals          id, type (weekly_volume|milestone|metric), sport, target_value, unit,
               period, deadline, achieved_at
insights       id, rule_id, date, severity, title, body, evidence_json, dismissed
ai_reports     id, week_start, model, payload_sent_json, response_md, created_at
planned_workouts (fase final)
raw_documents  kind, key, fetched_at, payload (zlib) — UNIQUE(kind, key)
sync_state     data_type PK, last_synced_at, last_cursor
sync_log       id, run_id, started_at, data_type, method, params_json, status, http_code,
               items, error, duration_ms
```

## 3. Plan de fases (el tuyo, con lo que añado)

- **F1 — Esqueleto y sincronización** 🛑. Monorepo, Makefile, `.env.example`, Alembic, `GarminSource` (A real, B stub, importación FIT/GPX/TCX/zip), `make probe`, sync incremental (12 meses al principio, re-sync de los últimos 3 días, backoff, pausa de 0,4 s, `sync_log`), progreso por SSE y resumen por consola. Tests con fixtures.
- **F2 — Analítica** 🛑. Todo el apartado 5 como funciones puras + tests + `/api/debug/activity/{id}` y `/api/debug/week/{date}`.
- **F3 — Sistema de diseño** 🛑. Tokens, glass, layout y página de muestra. La publicaré como vista previa para que la valides en el móvil.
- **F4 — Vistas principales** 🛑. **F5 — Secundarias, PWA, PIN, ⌘K** 🛑. **F6 — IA y pulido**.

Decisiones defendibles que ya tomo (configurables): GAP con el modelo de Minetti (2002), con la pendiente suavizada y acotada a ±45 %, porque está publicado y es reproducible (el de Strava no lo está del todo). ACWR por EWMA (Williams 2017). Zonas de FC Friel por % de LTHR. TRIMP de Banister con factor por sexo. Velocidad crítica por ajuste lineal distancia–tiempo con esfuerzos de 3 a 20 min.
