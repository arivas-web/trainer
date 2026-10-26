"""Configuración de la aplicación, leída de variables de entorno (.env.local en desarrollo,
variables de entorno de Vercel en producción). Nada de secretos en el código."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base de datos (Postgres de Supabase en producción; SQLite permitido para tests).
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/pulse"

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

    # Almacenamiento de FIT originales: "local" (data/fit) o "supabase" (bucket privado)
    storage_backend: str = "local"
    local_data_dir: Path = REPO_ROOT / "data"
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_fit_bucket: str = "fit"

    # Autenticación (Supabase Auth). ALLOWED_EMAIL = único usuario autorizado.
    auth_disabled: bool = False  # solo para desarrollo local
    supabase_jwt_secret: SecretStr | None = None  # HS256 (proyectos antiguos)
    allowed_email: str | None = None

    # Cifrado del token de Garmin cacheado en la base de datos (Fernet, base64 de 32 bytes).
    token_encryption_key: SecretStr | None = None

    # Secreto compartido con pg_cron para /api/sync/tick
    cron_secret: SecretStr | None = None

    # Zona horaria del atleta (para fechas "locales" de las métricas diarias)
    athlete_timezone: str = "Europe/Madrid"


@lru_cache
def get_settings() -> Settings:
    return Settings()
