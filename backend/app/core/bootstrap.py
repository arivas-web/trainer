"""Puesta a punto automática del esquema en el primer arranque (Vercel o local).

Así no hace falta pegar SQL en Supabase: la primera petición aplica las migraciones de
Alembic que falten. Un `pg_advisory_xact_lock` evita que dos funciones serverless que
arrancan a la vez migren en paralelo.
"""

import logging
import threading
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from alembic import command
from app.core.config import get_settings
from app.db import get_engine

log = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]
_LOCK_ID = 7_340_001  # identificador arbitrario del lock de migraciones
_done = False
_mutex = threading.Lock()


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["skip_logging_config"] = True
    return cfg


def ensure_schema() -> None:
    """Aplica las migraciones pendientes una vez por proceso. Idempotente."""
    global _done
    if _done or not get_settings().auto_migrate:
        return
    with _mutex:
        if _done:
            return
        cfg = alembic_config()
        head = ScriptDirectory.from_config(cfg).get_current_head()
        engine = get_engine()
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
        if current != head:
            log.info("Migrando esquema: %s -> %s", current, head)
            with engine.begin() as conn:
                if conn.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _LOCK_ID})
                cfg.attributes["connection"] = conn
                command.upgrade(cfg, "head")
        _done = True


def reset_for_tests() -> None:
    global _done
    _done = False
