"""Aplicación FastAPI. En Vercel la expone api/index.py; en local, `make dev`."""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import garmin, sync
from app.core.auth import User
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db import session_scope

setup_logging()

app = FastAPI(
    title="Pulse API",
    version="0.1.0",
    description="Laboratorio personal de rendimiento",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sync.router)
app.include_router(garmin.router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Estado de la puesta a punto (sin secretos): qué variables faltan y si la base responde."""
    s = get_settings()
    db_ok, db_error = True, None
    try:
        with session_scope() as ses:
            ses.execute(text("select 1"))
    except Exception as exc:
        db_ok, db_error = False, f"{type(exc).__name__}: {str(exc)[:200]}"
    checks = {
        "database": db_ok,
        "garmin_key": s.garmin_personal_api_key is not None,
        "supabase_url": bool(s.supabase_url),
        "supabase_anon_key": bool(s.supabase_anon_key),
        "allowed_email": bool(s.allowed_email) or s.auth_disabled,
        "storage": s.effective_storage == "supabase" or not s.on_vercel,
        "cron_secret": s.cron_secret is not None,
    }
    required = ("database", "garmin_key", "supabase_url", "supabase_anon_key", "allowed_email")
    return {
        "ok": all(checks[k] for k in required),
        "checks": checks,
        "required": list(required),
        "db_error": db_error,
        "storage": s.effective_storage,
    }


@app.get("/api/config")
def public_config() -> dict[str, Any]:
    """Configuración pública para el frontend (la clave anon de Supabase es pública)."""
    s = get_settings()
    return {
        "supabase_url": s.supabase_url,
        "supabase_anon_key": s.supabase_anon_key,
        "auth_disabled": s.auth_disabled,
    }


@app.get("/api/me")
def me(user: User) -> dict[str, Any]:
    return {"email": user.get("email")}
