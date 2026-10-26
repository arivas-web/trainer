"""Configuración de la aplicación, leída de variables de entorno (.env.local en desarrollo,
variables de entorno de Vercel en producción). Nada de secretos en el código."""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base de datos (Postgres de Supabase en producción; SQLite permitido para tests).
    # Acepta también POSTGRES_URL, la variable que crea la integración Supabase ↔ Vercel.
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/pulse",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )

    # Garmin Connect Personal API
    garmin_personal_api_key: SecretStr | None = None
    garmin_token_url: str = (
        "https://personal.connectapi.garmin.com/personalapitoken-service/"
        "personal-api/personal-api-key/token"
    )
    garmin_api_base: str = "https://personal.connectapi.garmin.com"
    # Ruta al archivo OpenAPI oficial de la Personal API (lo aporta Adrián).
    garmin_openapi_path: Path = (
        REPO_ROOT / "backend" / "app" / "sources" / "garmin_personal" / "openapi.json"
    )

    # Sincronización
    sync_pause_s: float = 0.4
    sync_max_retries: int = 5
    sync_initial_days: int = 365
    sync_resync_daily_days: int = 3
    sync_tick_budget_s: float = 45.0  # margen bajo el límite de duración de Vercel
    sync_auto_interval_h: float = 6.0  # 0 = sin sincronización automática

    # Almacenamiento de FIT originales: "local" (data/files), "supabase" (bucket privado) o
    # "auto" (supabase si hay credenciales, local si no).
    storage_backend: str = "auto"
    local_data_dir: Path = REPO_ROOT / "data"
    supabase_url: str | None = Field(
        default=None, validation_alias=AliasChoices("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
    )
    # Clave pública (anon/publishable): solo para el login del frontend; se sirve en /api/config.
    supabase_anon_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUPABASE_ANON_KEY",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY",
            "SUPABASE_PUBLISHABLE_KEY",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        ),
    )
    supabase_service_role_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"),
    )
    supabase_fit_bucket: str = "fit"

    # Autenticación (Supabase Auth). ALLOWED_EMAIL = único usuario autorizado.
    auth_disabled: bool = False  # solo para desarrollo local
    supabase_jwt_secret: SecretStr | None = None  # HS256 (proyectos antiguos)
    allowed_email: str | None = None

    # Cifrado del token de Garmin cacheado en la base de datos (Fernet, base64 de 32 bytes).
    token_encryption_key: SecretStr | None = None

    # Secreto compartido con pg_cron para /api/sync/tick
    cron_secret: SecretStr | None = None

    # Crear/actualizar el esquema automáticamente en el primer arranque (sin SQL a mano).
    auto_migrate: bool = True

    # Zona horaria del atleta (para fechas "locales" de las métricas diarias)
    athlete_timezone: str = "Europe/Madrid"

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        return normalize_db_url(v)

    @property
    def effective_storage(self) -> str:
        if self.storage_backend != "auto":
            return self.storage_backend
        return "supabase" if self.supabase_url and self.supabase_service_role_key else "local"

    @property
    def on_vercel(self) -> bool:
        return bool(os.environ.get("VERCEL"))


# Parámetros de conexión que entiende libpq/psycopg; el resto (p. ej. `supa=...` que añade
# Supabase) se descarta para que la conexión no falle.
_LIBPQ_PARAMS = {"sslmode", "sslrootcert", "connect_timeout", "application_name", "options"}


def normalize_db_url(url: str) -> str:
    """postgres://… o postgresql://… → postgresql+psycopg://…, sin parámetros desconocidos."""
    if url.startswith("sqlite"):
        return url
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix) :]
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k in _LIBPQ_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(query)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
