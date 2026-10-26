"""Mapeo declarativo de registros diarios de Garmin a `daily_metrics`.

Las rutas de campo viven en endpoints.toml ([kinds.<tipo>.fields]); aquí no se asume ningún
nombre de campo de Garmin. Lo que no esté mapeado queda a NULL ("sin datos").
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import DailyMetrics
from app.sources.garmin_personal.spec import KindSpec, dig

DAILY_COLUMNS = frozenset(
    c
    for c in (col.name for col in DailyMetrics.__table__.columns)
    if c not in ("date", "updated_at")
)


def record_date(kind: KindSpec, record: dict[str, Any]) -> date | None:
    raw = dig(record, kind.date_field)
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    if isinstance(raw, int | float):  # epoch s/ms
        ts = raw / 1000 if raw > 10**11 else raw
        return datetime.fromtimestamp(ts).date()
    return None


def map_daily_record(kind: KindSpec, record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column, fspec in kind.fields.items():
        if column not in DAILY_COLUMNS:
            raise ValueError(f"[kinds.{kind.name}.fields] columna desconocida: {column}")
        val = dig(record, fspec.path)
        if isinstance(val, int | float) and not isinstance(val, bool):
            val = val * fspec.scale
        out[column] = val
    return out


def upsert_daily(session: Session, day: date, values: dict[str, Any]) -> None:
    row = session.get(DailyMetrics, day)
    if row is None:
        row = DailyMetrics(date=day)
        session.add(row)
    for k, v in values.items():
        if v is not None:  # un tipo de dato no borra lo que trajo otro
            setattr(row, k, v)
