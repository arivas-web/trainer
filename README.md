# Pulse

Laboratorio personal de rendimiento sobre tus datos de Garmin: carga, intensidad, eficiencia,
predicciones y recuperación, con la explicación de cada número.

> Estado: **Fase 1** (esqueleto + sincronización). Ver `docs/fase-0-propuesta.md` para la
> arquitectura, el esquema y el plan.

## Arquitectura

| Pieza | Dónde |
|---|---|
| Frontend (Vite + React + TS + Tailwind) | Vercel, servicio `frontend` (ruta `/`) |
| API (FastAPI, Python 3.12) | Vercel, servicio `backend` (ruta `/api`) |
| Base de datos (Postgres) + login (Auth) + FIT originales (Storage) | Supabase (UE) |
| Sincronización automática | Vercel Cron diario → `/api/sync/tick` (opcional: `pg_cron` cada 10 min) |
| Datos | Garmin Connect **Personal API** (clave API personal) + importación FIT/GPX/TCX/zip |

Todas las tablas tienen RLS activado **sin políticas**: la clave pública de Supabase solo sirve
para el login; los datos solo los lee el backend.

## Despliegue (Vercel + Supabase)

Guía paso a paso, solo con el navegador: **[docs/guia-despliegue.md](docs/guia-despliegue.md)**.
En resumen: importar el repo en Vercel, conectar Supabase desde *Storage*, añadir
`GARMIN_PERSONAL_API_KEY`, `ALLOWED_EMAIL` y `CRON_SECRET`, y Redeploy. Las tablas se crean
solas en el primer arranque; si falta algo, la app lo dice en la pantalla de *Puesta a punto*.

## Desarrollo local

Requisitos: [uv](https://docs.astral.sh/uv/), Node 22, Docker (para Postgres).

```bash
make setup        # dependencias y .env.local a partir de .env.example
make db-up        # Postgres local en Docker
# Rellena .env.local: GARMIN_PERSONAL_API_KEY y AUTH_DISABLED=true (sin login en local)
make dev          # API en :8000 y web en :5173 (las tablas se crean solas)
```

| Comando | Qué hace |
|---|---|
| `make token-check` | Canjea tu clave por un token y muestra la **forma** de la respuesta (sin valores) |
| `make probe` | Lee el OpenAPI de la Personal API, llama a cada GET y guarda la forma de las respuestas en `data/probe_shapes.json` |
| `make sync` | Sincroniza (12 meses la primera vez; luego incremental) con barra de progreso y resumen |
| `make summary` | Resumen: actividades por deporte, fechas, qué métricas diarias llegan y cuáles no |
| `make import FILES="export.zip"` | Importa FIT/GPX/TCX sueltos, carpetas o el export completo de Garmin |
| `make migrate` / `make schema-sql` | Migraciones a mano / SQL del esquema para pegar en Supabase (alternativa al arranque automático) |
| `make test` / `make lint` | Tests (pytest) y build; ruff, mypy, eslint, prettier, tsc |

## Seguridad

- La clave de Garmin, la service role key y los secretos solo existen como variables de entorno
  (`.env.local` en local, Vercel en producción). `.env*` y `data/` están en `.gitignore`.
- El token de Garmin (24 h) se cachea **cifrado** (Fernet) en la base de datos, con `TOKEN_ENCRYPTION_KEY` o con una clave derivada de tu clave de Garmin.
- Los logs redactan cabeceras `Authorization` y campos tipo token o clave.
- `pre-commit install` añade los mismos checks que `make lint` y bloquea subir un `.env`.
