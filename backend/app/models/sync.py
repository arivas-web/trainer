import datetime as dt
from datetime import datetime
from typing import Any

from sqlalchemy import Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonType, utcnow


class RawDocument(Base):
    """Respuesta cruda de Garmin, para re-mapear sin volver a descargar."""

    __tablename__ = "raw_documents"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_raw_documents_kind_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(60))
    key: Mapped[str] = mapped_column(String(160))
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)
    payload: Mapped[Any] = mapped_column(JsonType)


class GarminToken(Base):
    """Access token de 24 h de la Personal API, cifrado. La clave en sí vive solo en env."""

    __tablename__ = "garmin_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    access_token_enc: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime]
    obtained_at: Mapped[datetime] = mapped_column(default=utcnow)


class SyncState(Base):
    """Último punto sincronizado por tipo de dato (sincronización incremental)."""

    __tablename__ = "sync_state"

    data_type: Mapped[str] = mapped_column(String(60), primary_key=True)
    synced_until: Mapped[dt.date | None]
    oldest_synced: Mapped[dt.date | None]
    last_run_at: Mapped[datetime | None]


class SyncJob(Base):
    """Trozo de trabajo de sincronización. Un tick procesa los pendientes que quepan en tiempo."""

    __tablename__ = "sync_jobs"
    __table_args__ = (Index("ix_sync_jobs_status", "status", "priority", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    data_type: Mapped[str] = mapped_column(String(60))
    range_start: Mapped[dt.date | None]
    range_end: Mapped[dt.date | None]
    ref: Mapped[str | None] = mapped_column(String(80))  # p. ej. id de actividad para el FIT
    priority: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|running|done|error
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]


class SyncLog(Base):
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    data_type: Mapped[str] = mapped_column(String(60))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(255))
    params_json: Mapped[dict[str, Any] | None]
    status: Mapped[str] = mapped_column(String(10))  # ok | error | skipped
    http_code: Mapped[int | None] = mapped_column(Integer)
    items: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float | None] = mapped_column(Float)
