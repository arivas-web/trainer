"""Entorno de Alembic: usa DATABASE_URL de la configuración de Pulse."""

from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (registra las tablas)
from alembic import context
from app.core.config import get_settings
from app.models.base import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=_url().startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    provided = config.attributes.get("connection")
    if provided is not None:  # app.core.bootstrap pasa su conexión (con el lock tomado)
        context.configure(connection=provided, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = _url()
    connect_args = {} if url.startswith("sqlite") else {"prepare_threshold": None}
    engine = create_engine(url, poolclass=NullPool, connect_args=connect_args)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
