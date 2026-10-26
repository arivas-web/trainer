# Despliegue en Vercel + Supabase, paso a paso (solo navegador)

Tiempo estimado: 15–20 min. No hace falta instalar nada ni pegar SQL: la API crea las tablas
sola en el primer arranque y, si falta algo, la web lo dice en una pantalla de **Puesta a punto**.

Son **dos proyectos de Vercel del mismo repo**:

- **backend**: la API, con raíz en `backend/`.
- **frontend**: la web, con raíz en `frontend/`.

Los valores secretos solo van en Vercel. Nunca los pegues en el chat ni en el repo.

## 1. Proyecto backend (la API)

1. <https://vercel.com/new> → **Import** `arivas-web/trainer`.
2. Vercel muestra las apps detectadas: elige **backend** (FastAPI). Si te pregunta por la *Root Directory*, es `backend`.
3. Nombre del proyecto: `pulse-api`, por ejemplo. Pulsa **Deploy**.
4. Al terminar, apunta su URL: será tu **URL_API** (`https://pulse-api-xxxx.vercel.app`).
   Si abres `URL_API/api/health` verás `"ok": false`. Es lo esperado.

## 2. Conectar Supabase al proyecto backend

Elige **una** opción:

**Opción A (recomendada).** En el proyecto `pulse-api` → pestaña **Storage** → **Create Database** →
**Supabase** → región **Frankfurt**, plan **Free** → conéctala al proyecto (*Production* y *Preview*).
Esto crea solas `POSTGRES_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `SUPABASE_SERVICE_ROLE_KEY`.

**Opción B: tu proyecto de Supabase existente.** En `pulse-api` → **Settings → Environment Variables**, añade:

| Variable | De dónde sale (en Supabase) |
|---|---|
| `DATABASE_URL` | Botón **Connect** → *Transaction pooler* (puerto 6543), con tu contraseña en lugar de `[YOUR-PASSWORD]` |
| `SUPABASE_URL` | *Project Settings → Data API → Project URL* |
| `SUPABASE_ANON_KEY` | *Project Settings → API Keys* → clave **publishable/anon** |
| `SUPABASE_SERVICE_ROLE_KEY` | Misma página → clave **secret/service_role** |

## 3. Tus tres variables (en el proyecto backend)

`pulse-api` → **Settings → Environment Variables** → añade (marca *Production* y *Preview*):

| Variable | Valor |
|---|---|
| `GARMIN_PERSONAL_API_KEY` | Tu clave API personal de Garmin |
| `ALLOWED_EMAIL` | Tu email (el único que podrá entrar) |
| `CRON_SECRET` | Una cadena aleatoria larga, por ejemplo de <https://www.random.org/strings/>. Activa la sincronización diaria automática |

Después: **Deployments** → ⋯ del último → **Redeploy**. Comprueba `URL_API/api/health`:
todos los `checks` deberían estar en `true`.

## 3 bis. Proyecto frontend (la web)

1. <https://vercel.com/new> → **Import** otra vez `arivas-web/trainer` → elige **frontend** (Vite).
2. Nombre: `pulse`, por ejemplo.
3. Antes de desplegar, en **Environment Variables**, añade:
   - `VITE_API_URL` = tu **URL_API** (sin `/` al final).
4. **Deploy**. Su URL es la de la app: **URL_APP** (`https://pulse-xxxx.vercel.app`).

## 4. Supabase: tu usuario y la URL de la app

En el panel de Supabase (en la opción A: proyecto backend → Storage → tu base de datos → **Open in Supabase**):

1. **Authentication → Users → Add user → Create new user**: tu email (el de `ALLOWED_EMAIL`),
   una contraseña cualquiera y marca **Auto Confirm User**.
2. **Authentication → Sign In / Providers**: desactiva **Allow new users to sign up**.
3. **Authentication → URL Configuration**:
   - *Site URL*: tu **URL_APP**.
   - *Redirect URLs*: añade tu **URL_APP** y `https://*.vercel.app/**`.

## 5. Entrar y comprobar

1. Abre **URL_APP** en el móvil. La pantalla de puesta a punto debe estar toda en ✓
   (en el primer acceso se crean las tablas, puede tardar unos segundos).
2. Escribe tu email → **Enviarme un enlace** → ábrelo desde el correo **en el mismo móvil**.
3. Tarjeta **Conexión con Garmin → Comprobar conexión**:
   - ✓ *Conectado*: mándame el bloque "Forma de la respuesta" (no contiene valores).
   - ✗: mándame el mensaje de error.
4. Sube un `.fit` en **Importar archivos**. Desde Garmin Connect web: actividad → ⚙ → *Exportar archivo original*.
5. Instala la app en el móvil: menú del navegador → **Añadir a pantalla de inicio**.

**Sincronizar** traerá datos de Garmin cuando haya mapeado los endpoints con el OpenAPI.

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| ✗ `database` con un error de conexión | Revisa `DATABASE_URL`/`POSTGRES_URL`; en la opción B, la contraseña y el puerto 6543. Después, **Redeploy** |
| ✗ en algo que ya has añadido | Las variables solo se aplican tras **Redeploy** (en el proyecto donde las añadiste) |
| "Falta VITE_API_URL" | Añádela en el proyecto **frontend** y haz Redeploy |
| Tras el enlace mágico, "Sesión no válida" | Añade `SUPABASE_JWT_SECRET` (*Supabase → Project Settings → JWT Keys → Legacy JWT secret*) y **Redeploy** |
| "Usuario no autorizado" | `ALLOWED_EMAIL` no coincide con el email con el que entras |
| No llega el correo | Mira en spam. El correo gratuito de Supabase permite pocos envíos por hora |
| La compilación falla en Vercel | Copia las últimas líneas del *Build Log* y pégamelas |

## Opcional: sincronizar más a menudo

El plan gratuito de Vercel solo permite un cron al día (05:17 UTC). Para avanzar la cola cada
10 minutos usa `pg_cron` de Supabase: ejecuta `supabase/02_setup.sql` en el **SQL Editor**,
sustituyendo `<CRON_SECRET>` y `<TU-APP>` (el subdominio del proyecto **backend**). Mientras tengas la app abierta, ella misma también
empuja la sincronización.
