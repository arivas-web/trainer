"""Aplicación FastAPI. En Vercel la expone api/index.py; en local, `make dev`."""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import sync
from app.core.auth import User
from app.core.config import get_settings
from app.core.logging import setup_logging

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


@app.get("/api/health")
def health() -> dict[str, Any]:
    s = get_settings()
    return {
        "ok": True,
        "garmin_key_configured": s.garmin_personal_api_key is not None,
        "storage": s.storage_backend,
    }


@app.get("/api/me")
def me(user: User) -> dict[str, Any]:
    return {"email": user.get("email")}
