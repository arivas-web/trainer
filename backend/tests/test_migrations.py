"""Las migraciones de Alembic producen exactamente el esquema de los modelos (en Postgres).
Se salta si no hay un Postgres de pruebas (TEST_POSTGRES_URL)."""

import os
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from alembic import command
from app.models import Base

PG_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/pulse_test"
)


def _pg_available() -> bool:
    try:
        with create_engine(PG_URL, connect_args={"connect_timeout": 2}).connect():
            return True
    except Exception:
        return False


@pytest.mark.skipif(not _pg_available(), reason="sin Postgres de pruebas")
def test_migrations_match_models() -> None:
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", PG_URL)
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        rls = conn.execute(
            text(
                "select count(*) from pg_class where relkind='r' and relnamespace="
                "'public'::regnamespace and not relrowsecurity"
            )
        ).scalar()
    assert diff == []
    assert rls == 0  # todas las tablas con RLS activado
    command.downgrade(cfg, "base")
