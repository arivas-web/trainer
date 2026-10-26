"""Guarda una actividad parseada en la base de datos (upsert idempotente).

Deduplicación: misma (source, external_id), mismo hash de archivo, o misma hora de inicio
(±60 s) y deporte. Así un FIT importado a mano y el mismo FIT sincronizado desde Garmin
acaban en una sola actividad. Los campos manuales (RPE, notas, carrera...) nunca se pisan.
"""

import hashlib
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.mapping import streams as stream_codec
from app.mapping.fit import ParsedActivity
from app.models import Activity, ActivityStream, Lap, SwimLength
from app.models.activity import SYNC_MANAGED_FIELDS

DEDUP_WINDOW = timedelta(seconds=60)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_existing(
    session: Session, source: str, external_id: str, file_hash: str | None, parsed: ParsedActivity
) -> Activity | None:
    act = session.scalar(
        select(Activity).where(Activity.source == source, Activity.external_id == external_id)
    )
    if act is None and file_hash:
        act = session.scalar(select(Activity).where(Activity.file_sha256 == file_hash))
    if act is None:
        start = parsed.summary["start_time_utc"]
        act = session.scalar(
            select(Activity).where(
                Activity.start_time_utc.between(start - DEDUP_WINDOW, start + DEDUP_WINDOW),
                Activity.sport == parsed.summary.get("sport"),
            )
        )
    return act


def upsert_activity(
    session: Session,
    parsed: ParsedActivity,
    *,
    source: str,
    external_id: str | None = None,
    file_bytes: bytes | None = None,
    storage_key: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[Activity, bool]:
    """Devuelve (actividad, creada)."""
    ext_id = external_id or parsed.external_id
    if not ext_id:
        raise ValueError("La actividad no tiene identificador externo")
    file_hash = sha256(file_bytes) if file_bytes else None
    act = find_existing(session, source, ext_id, file_hash, parsed)
    created = act is None
    if act is None:
        act = Activity(source=source, external_id=ext_id)
        session.add(act)

    values: dict[str, Any] = {**parsed.summary, **(extra or {})}
    if values.get("tz_offset_min") is not None:
        values["start_time_local"] = values["start_time_utc"] + timedelta(
            minutes=values["tz_offset_min"]
        )
    if file_hash:
        values["file_sha256"] = file_hash
    if storage_key:
        values["fit_storage_key"] = storage_key
    for key, val in values.items():
        if key in SYNC_MANAGED_FIELDS and key not in ("source", "external_id"):
            setattr(act, key, _clean(val))
    session.flush()

    session.execute(delete(Lap).where(Lap.activity_id == act.id))
    session.execute(delete(SwimLength).where(SwimLength.activity_id == act.id))
    for lap in parsed.laps:
        session.add(Lap(activity_id=act.id, **{k: _clean(v) for k, v in lap.items()}))
    for ln in parsed.lengths:
        session.add(SwimLength(activity_id=act.id, **{k: _clean(v) for k, v in ln.items()}))

    if parsed.streams and len(parsed.streams.get("time", [])) > 1:
        channels, n, blob = stream_codec.encode(parsed.streams)
        stream = session.get(ActivityStream, act.id)
        if stream is None:
            session.add(
                ActivityStream(activity_id=act.id, channels=channels, n_samples=n, data=blob)
            )
        else:
            stream.channels, stream.n_samples, stream.data = channels, n, blob
    session.flush()
    return act, created


def _clean(val: Any) -> Any:
    """Convierte tipos de numpy/enums de fitdecode a tipos básicos."""
    if val is None:
        return None
    if hasattr(val, "item"):
        val = val.item()
    if isinstance(val, float) and val != val:  # NaN
        return None
    return val
