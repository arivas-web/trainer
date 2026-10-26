"""Construye la fuente de Garmin y el worker con la configuración actual."""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core import crypto
from app.core.config import Settings, get_settings
from app.db import get_sessionmaker
from app.models import GarminToken
from app.sources.base import CallRecord
from app.sources.garmin_personal.auth import AccessToken, TokenProvider, request_token
from app.sources.garmin_personal.client import GarminPersonalSource
from app.sources.garmin_personal.spec import load_spec
from app.storage import get_storage
from app.sync.service import SyncWorker


class GarminNotConnectedError(RuntimeError):
    pass


def _db_token_cache(
    sf: sessionmaker[Session],
) -> tuple[Callable[[], AccessToken | None], Callable[[AccessToken], None]]:
    """Caché del token en la base de datos, cifrado. Sin TOKEN_ENCRYPTION_KEY no se guarda
    (se pedirá un token nuevo en cada invocación, que también funciona)."""

    def load() -> AccessToken | None:
        if not crypto.can_encrypt():
            return None
        with sf() as s:
            row = s.scalar(select(GarminToken).order_by(GarminToken.id.desc()).limit(1))
            if row is None:
                return None
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            try:
                return AccessToken(crypto.decrypt(row.access_token_enc), exp)
            except InvalidToken:  # la clave cambió: se pedirá un token nuevo
                return None

    def store(token: AccessToken) -> None:
        if not crypto.can_encrypt():
            return
        with sf.begin() as s:
            s.query(GarminToken).delete()
            s.add(
                GarminToken(
                    access_token_enc=crypto.encrypt(token.value),
                    expires_at=token.expires_at,
                    obtained_at=datetime.now(UTC),
                )
            )

    return load, store


def build_token_provider(
    settings: Settings, sf: sessionmaker[Session], http: httpx.Client
) -> TokenProvider:
    key = settings.garmin_personal_api_key
    if key is None:
        raise GarminNotConnectedError(
            "Falta GARMIN_PERSONAL_API_KEY (variable de entorno). Pulse no puede hablar con Garmin."
        )
    load, store = _db_token_cache(sf)
    return TokenProvider(
        fetch=lambda: request_token(http, settings.garmin_token_url, key.get_secret_value()),
        load_cached=load,
        store=store,
    )


def build_worker(
    settings: Settings | None = None, sf: sessionmaker[Session] | None = None
) -> tuple[SyncWorker, GarminPersonalSource]:
    settings = settings or get_settings()
    sf = sf or get_sessionmaker()
    http = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
    spec = load_spec()
    calls: list[CallRecord] = []
    source = GarminPersonalSource(
        spec,
        build_token_provider(settings, sf, http),
        settings.garmin_api_base,
        http=http,
        pause_s=settings.sync_pause_s,
        max_retries=settings.sync_max_retries,
        listener=calls.append,
    )
    worker = SyncWorker(sf, source, get_storage(settings), spec, calls)
    return worker, source
