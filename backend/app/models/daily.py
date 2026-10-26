import datetime as dt
from datetime import datetime
from typing import Any

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class DailyMetrics(Base):
    """Bienestar diario. Cada columna puede quedar a NULL si Garmin no la da ("sin datos")."""

    __tablename__ = "daily_metrics"

    date: Mapped[dt.date] = mapped_column(primary_key=True)
    resting_hr: Mapped[float | None] = mapped_column(Float)
    hrv_night_avg: Mapped[float | None] = mapped_column(Float)
    hrv_weekly_avg: Mapped[float | None] = mapped_column(Float)
    hrv_status: Mapped[str | None] = mapped_column(String(30))
    sleep_total_s: Mapped[float | None] = mapped_column(Float)
    sleep_deep_s: Mapped[float | None] = mapped_column(Float)
    sleep_light_s: Mapped[float | None] = mapped_column(Float)
    sleep_rem_s: Mapped[float | None] = mapped_column(Float)
    sleep_awake_s: Mapped[float | None] = mapped_column(Float)
    sleep_score: Mapped[float | None] = mapped_column(Float)
    sleep_start_local: Mapped[datetime | None]
    sleep_end_local: Mapped[datetime | None]
    body_battery_max: Mapped[float | None] = mapped_column(Float)
    body_battery_min: Mapped[float | None] = mapped_column(Float)
    body_battery_charged: Mapped[float | None] = mapped_column(Float)
    body_battery_drained: Mapped[float | None] = mapped_column(Float)
    stress_avg: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    active_kcal: Mapped[float | None] = mapped_column(Float)
    readiness_score: Mapped[float | None] = mapped_column(Float)
    readiness_factors_json: Mapped[dict[str, Any] | None]
    vo2max_run: Mapped[float | None] = mapped_column(Float)
    vo2max_bike: Mapped[float | None] = mapped_column(Float)
    fitness_age: Mapped[float | None] = mapped_column(Float)
    training_status: Mapped[str | None] = mapped_column(String(40))
    acute_load: Mapped[float | None] = mapped_column(Float)
    chronic_load: Mapped[float | None] = mapped_column(Float)
    respiration_avg: Mapped[float | None] = mapped_column(Float)
    spo2_avg: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class DailyLoad(Base):
    """Carga diaria materializada (Fase 2)."""

    __tablename__ = "daily_load"

    date: Mapped[dt.date] = mapped_column(primary_key=True)
    load_total: Mapped[float] = mapped_column(Float, default=0.0)
    load_by_sport_json: Mapped[dict[str, Any] | None]
    ctl: Mapped[float | None] = mapped_column(Float)
    atl: Mapped[float | None] = mapped_column(Float)
    tsb: Mapped[float | None] = mapped_column(Float)
    acwr: Mapped[float | None] = mapped_column(Float)
    ramp_rate_7d: Mapped[float | None] = mapped_column(Float)
    monotony_7d: Mapped[float | None] = mapped_column(Float)
    strain_7d: Mapped[float | None] = mapped_column(Float)
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
