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


def test_schema_sql_is_up_to_date() -> None:
    """supabase/01_schema.sql (lo que Adrián pega en Supabase) coincide con las migraciones."""
    import subprocess

    root = Path(__file__).resolve().parents[2]
    committed = (root / "supabase" / "01_schema.sql").read_text()
    out = subprocess.run(
        ["alembic", "upgrade", "head", "--sql"],
        cwd=root / "backend",
        env={**os.environ, "DATABASE_URL": "postgresql+psycopg://x@localhost/x"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert committed.split("\n\n", 1)[1] == out, "Ejecuta `make schema-sql`"


@pytest.mark.skipif(not _pg_available(), reason="sin Postgres de pruebas")
def test_auto_migrate_on_first_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import bootstrap
    from app.core.config import get_settings
    from app.db import get_engine, get_sessionmaker, session_scope

    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    monkeypatch.setenv("DATABASE_URL", PG_URL.replace("postgresql+psycopg", "postgres"))
    monkeypatch.setenv("AUTO_MIGRATE", "true")
    for f in (get_settings, get_engine, get_sessionmaker):
        f.cache_clear()
    bootstrap.reset_for_tests()
    with session_scope() as s:
        n = s.execute(text("select count(*) from activities")).scalar()
    assert n == 0
    with session_scope():  # segunda vez: no-op
        pass
    get_engine().dispose()
    bootstrap.reset_for_tests()


def test_normalize_db_url() -> None:
    from app.core.config import normalize_db_url

    raw = "postgres://u:p@aws-0-eu.pooler.supabase.com:6543/postgres?sslmode=require&supa=base-pooler.x"
    assert normalize_db_url(raw) == (
        "postgresql+psycopg://u:p@aws-0-eu.pooler.supabase.com:6543/postgres?sslmode=require"
    )
    assert normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"
