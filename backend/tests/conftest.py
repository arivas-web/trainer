from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.models import Base


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cada test con su SQLite temporal y sin credenciales reales."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pulse.db'}")
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "test-key")
    monkeypatch.setenv("SYNC_PAUSE_S", "0")
    monkeypatch.setenv("AUTO_MIGRATE", "false")  # los tests crean el esquema con create_all
    for var in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "POSTGRES_URL", "VERCEL"):
        monkeypatch.delenv(var, raising=False)
    for f in (get_settings, get_engine, get_sessionmaker):
        f.cache_clear()
    Base.metadata.create_all(get_engine())
    yield
    get_engine().dispose()
    for f in (get_settings, get_engine, get_sessionmaker):
        f.cache_clear()


@pytest.fixture
def sf() -> sessionmaker[Session]:
    return get_sessionmaker()


@pytest.fixture
def session(sf: sessionmaker[Session]) -> Iterator[Session]:
    with sf() as s:
        yield s
