# Despliegue en Vercel + Supabase, paso a paso (solo navegador)

Tiempo estimado: 15 min. No hace falta instalar nada ni pegar SQL: la app crea las tablas sola
en el primer arranque y, si falta algo, te dice qué en una pantalla de **Puesta a punto**.

Los valores secretos solo van en Vercel. Nunca los pegues en el chat ni en el repo.

## 1. Importar el repo en Vercel

1. Entra en <https://vercel.com/new>.
2. En *Import Git Repository*, elige **arivas-web/trainer**.
   Si no aparece: *Adjust GitHub App Permissions* → dale acceso a ese repo.
3. *Framework Preset*: **Other**. No cambies nada más: los comandos están en `vercel.json`.
4. Pulsa **Deploy** y espera 2–3 min.
5. Abre la URL que te da (`https://trainer-xxxx.vercel.app`). Verás **Puesta a punto** con ✗ en rojo. Es lo esperado.

## 2. Conectar Supabase

Elige **una** opción:

### Opción A (recomendada): desde Vercel

1. En tu proyecto de Vercel → pestaña **Storage** → **Create Database** → **Supabase** → *Continue*.
2. Región **Frankfurt (eu-central-1)**, plan **Free** → *Create*.
3. Cuando te pregunte, conéctala al proyecto `trainer` (entornos *Production* y *Preview*).
   Esto crea automáticamente `POSTGRES_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY`, etc.

### Opción B: con tu proyecto de Supabase existente

En Vercel → **Settings → Environment Variables**, añade:

| Variable | De dónde sale (en Supabase) |
|---|---|
| `DATABASE_URL` | Botón **Connect** → *Transaction pooler* (puerto 6543), con tu contraseña en lugar de `[YOUR-PASSWORD]` |
| `SUPABASE_URL` | *Project Settings → Data API → Project URL* |
| `SUPABASE_ANON_KEY` | *Project Settings → API Keys* → clave **publishable/anon** |
| `SUPABASE_SERVICE_ROLE_KEY` | Misma página → clave **secret/service_role** |

## 3. Tus tres variables

Vercel → **Settings → Environment Variables** → añade (marca *Production* y *Preview*):

| Variable | Valor |
|---|---|
| `GARMIN_PERSONAL_API_KEY` | Tu clave API personal de Garmin |
| `ALLOWED_EMAIL` | Tu email (el único que podrá entrar) |
| `CRON_SECRET` | Una cadena aleatoria larga, por ejemplo de <https://www.random.org/strings/> (20 caracteres, letras y números). Activa la sincronización automática diaria |

Después: pestaña **Deployments** → los tres puntos del último → **Redeploy**.

## 4. Supabase: tu usuario y la URL de la app

En el panel de Supabase (en la opción A, Vercel → Storage → tu base de datos → **Open in Supabase**):

1. **Authentication → Users → Add user → Create new user**: tu email (el de `ALLOWED_EMAIL`),
   una contraseña cualquiera y marca **Auto Confirm User**.
2. **Authentication → Sign In / Providers**: desactiva **Allow new users to sign up**.
3. **Authentication → URL Configuration**:
   - *Site URL*: tu URL de Vercel.
   - *Redirect URLs*: añade tu URL de Vercel y `https://*.vercel.app/**`.

## 5. Entrar y comprobar

1. Abre la URL de Vercel en el móvil. La pantalla de puesta a punto debe estar toda en ✓
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
| ✗ en algo que ya has añadido | Las variables solo se aplican tras **Redeploy** |
| Tras el enlace mágico, "Sesión no válida" | Añade `SUPABASE_JWT_SECRET` (*Supabase → Project Settings → JWT Keys → Legacy JWT secret*) y **Redeploy** |
| "Usuario no autorizado" | `ALLOWED_EMAIL` no coincide con el email con el que entras |
| No llega el correo | Mira en spam. El correo gratuito de Supabase permite pocos envíos por hora |
| La compilación falla en Vercel | Copia las últimas líneas del *Build Log* y pégamelas |

## Opcional: sincronizar más a menudo

El plan gratuito de Vercel solo permite un cron al día (05:17 UTC). Para avanzar la cola cada
10 minutos usa `pg_cron` de Supabase: ejecuta `supabase/02_setup.sql` en el **SQL Editor**,
sustituyendo `<CRON_SECRET>` y `<TU-APP>`. Mientras tengas la app abierta, ella misma también
empuja la sincronización.
