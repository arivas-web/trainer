import datetime as dt
from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class AthleteThresholds(Base):
    """Umbrales fisiológicos con vigencia: cada actividad usa la fila con el mayor
    effective_from <= fecha de la actividad."""

    __tablename__ = "athlete_thresholds"

    id: Mapped[int] = mapped_column(primary_key=True)
    effective_from: Mapped[dt.date] = mapped_column(unique=True)
    hr_max: Mapped[float | None] = mapped_column(Float)
    hr_rest: Mapped[float | None] = mapped_column(Float)
    lthr: Mapped[float | None] = mapped_column(Float)
    threshold_pace_s_km: Mapped[float | None] = mapped_column(Float)
    css_s_100m: Mapped[float | None] = mapped_column(Float)
    ftp_w: Mapped[float | None] = mapped_column(Float)
    running_ftp_w: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    notes: Mapped[str | None] = mapped_column(Text)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Race(Base):
    __tablename__ = "races"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    date: Mapped[dt.date | None]  # el 70.3 aún no tiene fecha
    distance_m: Mapped[float | None] = mapped_column(Float)
    format: Mapped[str] = mapped_column(String(30))  # run | tri_70_3 | trail ...
    target_time_s: Mapped[float | None] = mapped_column(Float)
    priority: Mapped[str] = mapped_column(String(1), default="A")
    result_activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(30))  # weekly_volume | milestone | metric
    sport: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    target_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    period: Mapped[str | None] = mapped_column(String(20))
    deadline: Mapped[dt.date | None]
    achieved_at: Mapped[dt.date | None]


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(80))
    date: Mapped[dt.date]
    severity: Mapped[str] = mapped_column(String(10))  # info | positive | warning | alert
    priority: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[dict[str, Any] | None]
    dismissed: Mapped[bool] = mapped_column(default=False)


class AiReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[dt.date]
    model: Mapped[str] = mapped_column(String(80))
    payload_sent_json: Mapped[dict[str, Any]]
    response_md: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
