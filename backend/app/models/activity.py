import datetime as dt
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow


class Gear(Base):
    """Material. La Personal API no expone el material: se gestiona a mano en Pulse."""

    __tablename__ = "gear"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))  # shoes | bike | other
    initial_km: Mapped[float] = mapped_column(Float, default=0.0)
    limit_km: Mapped[float | None] = mapped_column(Float, default=700.0)
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    # Reglas de asignación automática, p. ej. {"sports": ["trail_running"]}
    auto_assign_rule: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_activities_source_external_id"),
        Index("ix_activities_sport_start", "sport", "start_time_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # garmin_personal | fit_import | gpx_import...
    external_id: Mapped[str] = mapped_column(String(64))
    # Huella del FIT para deduplicar importaciones manuales contra lo sincronizado.
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)

    start_time_utc: Mapped[datetime] = mapped_column(index=True)
    start_time_local: Mapped[datetime | None]  # hora de pared (sin tz) guardada como naive-UTC
    tz_offset_min: Mapped[int | None] = mapped_column(Integer)

    sport: Mapped[str] = mapped_column(String(40))
    sub_sport: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str | None] = mapped_column(String(200))
    device: Mapped[str | None] = mapped_column(String(80))

    distance_m: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    moving_s: Mapped[float | None] = mapped_column(Float)
    elev_gain_m: Mapped[float | None] = mapped_column(Float)
    elev_loss_m: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    avg_speed: Mapped[float | None] = mapped_column(Float)  # m/s
    max_speed: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)  # pasos/min (carrera) o rpm
    avg_power: Mapped[float | None] = mapped_column(Float)
    max_power: Mapped[float | None] = mapped_column(Float)
    normalized_power: Mapped[float | None] = mapped_column(Float)
    aerobic_te: Mapped[float | None] = mapped_column(Float)
    anaerobic_te: Mapped[float | None] = mapped_column(Float)
    garmin_training_load: Mapped[float | None] = mapped_column(Float)
    vo2max: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    avg_temp_c: Mapped[float | None] = mapped_column(Float)
    weather_json: Mapped[dict[str, Any] | None]
    gear_id: Mapped[int | None] = mapped_column(ForeignKey("gear.id", ondelete="SET NULL"))

    has_streams: Mapped[bool] = mapped_column(Boolean, default=False)
    has_power: Mapped[bool] = mapped_column(Boolean, default=False)
    has_running_dynamics: Mapped[bool] = mapped_column(Boolean, default=False)
    fit_storage_key: Mapped[str | None] = mapped_column(String(255))

    # Campos manuales: la sincronización NUNCA los sobrescribe.
    is_race: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trail_override: Mapped[bool | None] = mapped_column(Boolean)
    excluded_from_analytics: Mapped[bool] = mapped_column(Boolean, default=False)
    rpe: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    laps: Mapped[list["Lap"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", order_by="Lap.idx"
    )
    stream: Mapped["ActivityStream | None"] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )


# Campos que rellena la sincronización; el resto (manuales) no se tocan al actualizar.
SYNC_MANAGED_FIELDS = frozenset(
    c
    for c in (col.name for col in Activity.__table__.columns)
    if c
    not in {
        "id",
        "is_race",
        "is_trail_override",
        "excluded_from_analytics",
        "rpe",
        "notes",
        "gear_id",
        "created_at",
        "updated_at",
    }
)


class ActivityStream(Base):
    """Streams por canal: float32 little-endian comprimidos con zlib (ver app.mapping.streams)."""

    __tablename__ = "activity_streams"

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True
    )
    n_samples: Mapped[int] = mapped_column(Integer)
    channels: Mapped[list[Any]]
    data: Mapped[bytes]
    schema_version: Mapped[int] = mapped_column(Integer, default=1)

    activity: Mapped[Activity] = relationship(back_populates="stream")


class Lap(Base):
    __tablename__ = "laps"
    __table_args__ = (UniqueConstraint("activity_id", "idx", name="uq_laps_activity_idx"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    start_offset_s: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    moving_s: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    avg_speed: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)
    avg_power: Mapped[float | None] = mapped_column(Float)
    elev_gain_m: Mapped[float | None] = mapped_column(Float)
    elev_loss_m: Mapped[float | None] = mapped_column(Float)
    intensity: Mapped[str | None] = mapped_column(String(20))  # active | rest | warmup...
    # Natación
    swim_stroke: Mapped[str | None] = mapped_column(String(20))
    num_lengths: Mapped[int | None] = mapped_column(Integer)
    total_strokes: Mapped[int | None] = mapped_column(Integer)

    activity: Mapped[Activity] = relationship(back_populates="laps")


class SwimLength(Base):
    __tablename__ = "swim_lengths"
    __table_args__ = (Index("ix_swim_lengths_activity", "activity_id", "idx"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"))
    lap_idx: Mapped[int | None] = mapped_column(Integer)
    idx: Mapped[int] = mapped_column(Integer)
    start_offset_s: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    length_type: Mapped[str | None] = mapped_column(String(10))  # active | idle
    stroke_type: Mapped[str | None] = mapped_column(String(20))
    strokes: Mapped[int | None] = mapped_column(Integer)
    pool_length_m: Mapped[float | None] = mapped_column(Float)


class ComputedActivityMetrics(Base):
    """Métricas derivadas (Fase 2). Se recalculan cuando cambia inputs_hash."""

    __tablename__ = "computed_activity_metrics"

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True
    )
    inputs_hash: Mapped[str] = mapped_column(String(64))
    algo_version: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(default=utcnow)
    load_value: Mapped[float | None] = mapped_column(Float)
    load_method: Mapped[str | None] = mapped_column(String(20))
    trimp: Mapped[float | None] = mapped_column(Float)
    hrtss: Mapped[float | None] = mapped_column(Float)
    rtss: Mapped[float | None] = mapped_column(Float)
    tss_power: Mapped[float | None] = mapped_column(Float)
    intensity_factor: Mapped[float | None] = mapped_column(Float)
    gap_avg_speed: Mapped[float | None] = mapped_column(Float)
    efficiency_factor: Mapped[float | None] = mapped_column(Float)
    decoupling_pct: Mapped[float | None] = mapped_column(Float)
    hr_drift_pct: Mapped[float | None] = mapped_column(Float)
    vam_m_h: Mapped[float | None] = mapped_column(Float)
    walk_pct: Mapped[float | None] = mapped_column(Float)
    is_trail: Mapped[bool | None] = mapped_column(Boolean)
    pace_at_hr_json: Mapped[dict[str, Any] | None]
    zone_time_json: Mapped[dict[str, Any] | None]
    extra_json: Mapped[dict[str, Any] | None]


class BestEffort(Base):
    __tablename__ = "best_efforts"
    __table_args__ = (
        Index("ix_best_efforts_rank", "sport", "kind", "target", "value"),
        UniqueConstraint("activity_id", "kind", "target", name="uq_best_efforts_activity_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"))
    sport: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(10))  # distance | duration
    target: Mapped[float] = mapped_column(Float)  # metros o segundos
    value: Mapped[float] = mapped_column(Float)  # segundos (distancia) o metros/vatios (duración)
    start_offset_s: Mapped[float | None] = mapped_column(Float)
    date: Mapped[dt.date]


class PersonalRecord(Base):
    __tablename__ = "personal_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(10))
    target: Mapped[float] = mapped_column(Float)
    value: Mapped[float] = mapped_column(Float)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL")
    )
    date: Mapped[dt.date]
    source: Mapped[str] = mapped_column(String(20), default="computed")
