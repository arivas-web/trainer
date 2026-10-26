# Pulse

Laboratorio personal de rendimiento sobre tus datos de Garmin: carga, intensidad, eficiencia,
predicciones y recuperación, con la explicación de cada número.

> Estado: **Fase 1** (esqueleto + sincronización). Ver `docs/fase-0-propuesta.md` para la
> arquitectura, el esquema y el plan.

## Arquitectura

| Pieza | Dónde |
|---|---|
| Frontend (Vite + React + TS + Tailwind) | Vercel (estático) |
| API (FastAPI, Python 3.12) | Vercel, función `api/index.py` |
| Base de datos (Postgres) + login (Auth) + FIT originales (Storage) | Supabase (UE) |
| Sincronización automática | `pg_cron` de Supabase → `POST /api/sync/tick` cada 10 min |
| Datos | Garmin Connect **Personal API** (clave API personal) + importación FIT/GPX/TCX/zip |

Todas las tablas tienen RLS activado **sin políticas**: la clave pública de Supabase solo sirve
para el login; los datos solo los lee el backend.

## Desarrollo local

Requisitos: [uv](https://docs.astral.sh/uv/), Node 22, Docker (para Postgres).

```bash
make setup        # dependencias + .env.local y frontend/.env.local a partir de los ejemplos
make db-up        # Postgres local en Docker
make migrate      # crea las tablas
make key          # genera TOKEN_ENCRYPTION_KEY (y otra para CRON_SECRET)
# Rellena .env.local: GARMIN_PERSONAL_API_KEY, TOKEN_ENCRYPTION_KEY, AUTH_DISABLED=true
# y en frontend/.env.local: VITE_AUTH_DISABLED=true
make dev          # API en :8000 y web en :5173
```

Otros comandos: `make help`.

| Comando | Qué hace |
|---|---|
| `make token-check` | Canjea tu clave por un token y muestra la **forma** de la respuesta (sin valores) |
| `make probe` | Lee el OpenAPI de la Personal API, llama a cada GET y guarda la forma de las respuestas en `data/probe_shapes.json` |
| `make sync` | Sincroniza (12 meses la primera vez; luego incremental) con barra de progreso y resumen |
| `make summary` | Resumen: actividades por deporte, fechas, qué métricas diarias llegan y cuáles no |
| `make import FILES="export.zip"` | Importa FIT/GPX/TCX sueltos, carpetas o el export completo de Garmin |
| `make test` / `make lint` | Tests (pytest) y build; ruff, mypy, eslint, prettier, tsc |

## Despliegue (Supabase + Vercel, plan gratuito)

1. **Supabase** → *New project*, región **Frankfurt (eu-central-1)**.
   - *Authentication → Sign In / Providers → Email*: activado. Desactiva *Allow new users to sign up*
     y crea tu usuario en *Authentication → Users → Add user* con tu email.
   - *Authentication → URL Configuration*: *Site URL* = la URL de Vercel.
   - Copia la cadena del **Transaction pooler** (*Connect*, puerto 6543) y cambia el prefijo a
     `postgresql+psycopg://`.
2. **Migraciones** desde tu ordenador: `DATABASE_URL="<cadena del pooler>" make migrate`.
3. **Vercel** → *Add New Project* → importa este repo. La configuración está en `vercel.json`.
   En *Settings → Environment Variables* añade las de `.env.example` con
   `STORAGE_BACKEND=supabase` y `AUTH_DISABLED=false`, y las públicas del frontend
   (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`).
4. **Supabase → SQL Editor**: ejecuta `supabase/setup.sql` sustituyendo `<CRON_SECRET>` y
   `<TU-APP>`. Crea el bucket privado `fit` y programa la sincronización.
5. Abre la URL de Vercel en el móvil, pide el enlace mágico y pulsa **Sincronizar**.

## Seguridad

- La clave de Garmin, la service role key y los secretos solo existen como variables de entorno
  (`.env.local` en local, Vercel en producción). `.env*` y `data/` están en `.gitignore`.
- El token de Garmin (24 h) se cachea **cifrado** (Fernet) en la base de datos.
- Los logs redactan cabeceras `Authorization` y campos tipo token o clave.
- `pre-commit install` añade los mismos checks que `make lint` y bloquea subir un `.env`.
