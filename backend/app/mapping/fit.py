"""Parser de actividades FIT (fitdecode) al modelo canónico de Pulse.

Referencia de campos y unidades: FIT SDK Profile (mensajes file_id, activity, session, lap,
length, record, device_info). fitdecode ya aplica escala y offset, así que velocidades
llegan en m/s, distancias y altitudes en m, stance_time en ms, vertical_oscillation y
step_length en mm.
"""

import io
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import fitdecode
import numpy as np

from app.mapping.streams import FloatArray

SEMICIRCLE_TO_DEG = 180.0 / 2**31
RUNNING_SPORTS = {"running", "walking", "hiking", "trail_running"}


@dataclass
class ParsedActivity:
    summary: dict[str, Any]
    laps: list[dict[str, Any]] = field(default_factory=list)
    lengths: list[dict[str, Any]] = field(default_factory=list)
    streams: dict[str, FloatArray] = field(default_factory=dict)
    external_id: str | None = None


def _v(msg: fitdecode.FitDataMessage, *names: str) -> Any:
    """Primer campo presente y no nulo entre `names`."""
    for n in names:
        if msg.has_field(n):
            val = msg.get_value(n, fallback=None)
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                return val
    return None


def _str(val: Any) -> str | None:
    return None if val is None else str(val)


def _utc(val: Any) -> datetime | None:
    if not isinstance(val, datetime):
        return None
    return val if val.tzinfo else val.replace(tzinfo=UTC)


def parse_fit(data: bytes) -> ParsedActivity:
    file_id: dict[str, Any] = {}
    sessions: list[fitdecode.FitDataMessage] = []
    laps: list[fitdecode.FitDataMessage] = []
    lengths: list[fitdecode.FitDataMessage] = []
    records: list[fitdecode.FitDataMessage] = []
    activity_msg: fitdecode.FitDataMessage | None = None
    device_name: str | None = None

    with fitdecode.FitReader(
        io.BytesIO(data),
        check_crc=fitdecode.CrcCheck.WARN,
        error_handling=fitdecode.ErrorHandling.WARN,
    ) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            name = frame.name
            if name == "file_id":
                file_id = {
                    "type": _str(_v(frame, "type")),
                    "manufacturer": _str(_v(frame, "manufacturer")),
                    "product": _str(_v(frame, "garmin_product", "product_name", "product")),
                    "serial": _v(frame, "serial_number"),
                    "time_created": _utc(_v(frame, "time_created")),
                }
            elif name == "session":
                sessions.append(frame)
            elif name == "lap":
                laps.append(frame)
            elif name == "length":
                lengths.append(frame)
            elif name == "record":
                records.append(frame)
            elif name == "activity":
                activity_msg = frame
            elif (
                name == "device_info"
                and device_name is None
                and _v(frame, "device_index") in (0, "creator")
            ):
                device_name = _str(_v(frame, "garmin_product", "product_name", "product"))

    if file_id.get("type") not in (None, "activity"):
        raise ValueError(f"El FIT no es una actividad (type={file_id.get('type')})")
    if not sessions and not records:
        raise ValueError("FIT sin sesiones ni registros")

    session = sessions[0] if sessions else None
    sport = _str(_v(session, "sport")) if session else None
    sub_sport = _str(_v(session, "sub_sport")) if session else None
    is_running = (sport or "") in RUNNING_SPORTS

    streams = _streams(records, is_running)
    start = _utc(_v(session, "start_time")) if session else None
    if start is None and records:
        start = _utc(_v(records[0], "timestamp"))
    if start is None:
        start = file_id.get("time_created")
    if start is None:
        raise ValueError("No se puede determinar la hora de inicio del FIT")

    tz_offset_min: int | None = None
    if activity_msg is not None:
        ts, local = _v(activity_msg, "timestamp"), _v(activity_msg, "local_timestamp")
        if isinstance(ts, datetime) and isinstance(local, datetime):
            delta = local.replace(tzinfo=None) - ts.replace(tzinfo=None)
            tz_offset_min = round(delta.total_seconds() / 60 / 15) * 15

    summary: dict[str, Any] = {
        "start_time_utc": start,
        "tz_offset_min": tz_offset_min,
        "sport": sport or "generic",
        "sub_sport": sub_sport,
        "device": device_name or file_id.get("product"),
    }
    if session is not None:
        cad = _v(session, "avg_running_cadence", "avg_cadence")
        frac = _v(session, "avg_fractional_cadence") or 0.0
        summary.update(
            distance_m=_v(session, "total_distance"),
            duration_s=_v(session, "total_elapsed_time"),
            moving_s=_v(session, "total_timer_time"),
            elev_gain_m=_v(session, "total_ascent"),
            elev_loss_m=_v(session, "total_descent"),
            avg_hr=_v(session, "avg_heart_rate"),
            max_hr=_v(session, "max_heart_rate"),
            avg_speed=_v(session, "enhanced_avg_speed", "avg_speed"),
            max_speed=_v(session, "enhanced_max_speed", "max_speed"),
            avg_cadence=None if cad is None else (cad + frac) * (2 if is_running else 1),
            avg_power=_v(session, "avg_power"),
            max_power=_v(session, "max_power"),
            normalized_power=_v(session, "normalized_power"),
            aerobic_te=_v(session, "total_training_effect"),
            anaerobic_te=_v(session, "total_anaerobic_training_effect"),
            garmin_training_load=_v(session, "training_load_peak"),
            calories=_v(session, "total_calories"),
            avg_temp_c=_v(session, "avg_temperature"),
        )
        pool = _v(session, "pool_length")
    else:
        pool = None

    if summary.get("avg_speed") is None and summary.get("distance_m") and summary.get("moving_s"):
        summary["avg_speed"] = summary["distance_m"] / summary["moving_s"]
    if "time" in streams and len(streams["time"]):
        t = streams["time"]
        if summary.get("duration_s") is None:
            summary["duration_s"] = float(t[-1] - t[0])
    summary["has_streams"] = bool(streams) and len(streams.get("time", [])) > 1
    summary["has_power"] = "power" in streams or summary.get("avg_power") is not None
    summary["has_running_dynamics"] = any(
        c in streams for c in ("ground_contact_time", "vertical_oscillation", "vertical_ratio")
    )

    parsed = ParsedActivity(summary=summary, streams=streams)
    parsed.external_id = _external_id(file_id, start)
    parsed.laps = [_lap(i, m, start, is_running) for i, m in enumerate(laps)]
    parsed.lengths = [_length(i, m, start, pool) for i, m in enumerate(lengths)]
    return parsed


def _external_id(file_id: dict[str, Any], start: datetime) -> str:
    serial = file_id.get("serial") or "x"
    created = file_id.get("time_created") or start
    return f"fit:{serial}:{int(created.timestamp())}"


def _lap(idx: int, m: fitdecode.FitDataMessage, start: datetime, running: bool) -> dict[str, Any]:
    lap_start = _utc(_v(m, "start_time"))
    cad = _v(m, "avg_running_cadence", "avg_cadence")
    frac = _v(m, "avg_fractional_cadence") or 0.0
    return {
        "idx": idx,
        "start_offset_s": (lap_start - start).total_seconds() if lap_start else None,
        "duration_s": _v(m, "total_elapsed_time"),
        "moving_s": _v(m, "total_timer_time"),
        "distance_m": _v(m, "total_distance"),
        "avg_speed": _v(m, "enhanced_avg_speed", "avg_speed"),
        "avg_hr": _v(m, "avg_heart_rate"),
        "max_hr": _v(m, "max_heart_rate"),
        "avg_cadence": None if cad is None else (cad + frac) * (2 if running else 1),
        "avg_power": _v(m, "avg_power"),
        "elev_gain_m": _v(m, "total_ascent"),
        "elev_loss_m": _v(m, "total_descent"),
        "intensity": _str(_v(m, "intensity")),
        "swim_stroke": _str(_v(m, "swim_stroke")),
        "num_lengths": _v(m, "num_active_lengths", "num_lengths"),
        "total_strokes": _v(m, "total_strokes"),
    }


def _length(
    idx: int, m: fitdecode.FitDataMessage, start: datetime, pool: float | None
) -> dict[str, Any]:
    ls = _utc(_v(m, "start_time"))
    return {
        "idx": idx,
        "start_offset_s": (ls - start).total_seconds() if ls else None,
        "duration_s": _v(m, "total_elapsed_time"),
        "length_type": _str(_v(m, "length_type")),
        "stroke_type": _str(_v(m, "swim_stroke")),
        "strokes": _v(m, "total_strokes"),
        "pool_length_m": pool,
    }


_RECORD_FIELDS: dict[str, tuple[str, ...]] = {
    "distance": ("distance",),
    "altitude": ("enhanced_altitude", "altitude"),
    "hr": ("heart_rate",),
    "speed": ("enhanced_speed", "speed"),
    "power": ("power",),
    "temperature": ("temperature",),
    "ground_contact_time": ("stance_time",),
    "vertical_oscillation": ("vertical_oscillation",),
    "vertical_ratio": ("vertical_ratio",),
}


def _streams(records: list[fitdecode.FitDataMessage], running: bool) -> dict[str, FloatArray]:
    rows = [r for r in records if isinstance(_v(r, "timestamp"), datetime)]
    if not rows:
        return {}
    t0 = _utc(_v(rows[0], "timestamp"))
    assert t0 is not None
    n = len(rows)
    out: dict[str, FloatArray] = {k: np.full(n, np.nan) for k in (*_RECORD_FIELDS, "time")}
    out.update({k: np.full(n, np.nan) for k in ("lat", "lon", "cadence", "stride_length")})
    for i, r in enumerate(rows):
        ts = _utc(_v(r, "timestamp"))
        assert ts is not None
        out["time"][i] = (ts - t0).total_seconds()
        for key, names in _RECORD_FIELDS.items():
            val = _v(r, *names)
            if isinstance(val, int | float):
                out[key][i] = float(val)
        lat, lon = _v(r, "position_lat"), _v(r, "position_long")
        if isinstance(lat, int) and isinstance(lon, int):
            out["lat"][i] = lat * SEMICIRCLE_TO_DEG
            out["lon"][i] = lon * SEMICIRCLE_TO_DEG
        cad = _v(r, "cadence")
        if isinstance(cad, int | float):
            frac = _v(r, "fractional_cadence") or 0.0
            out["cadence"][i] = (cad + frac) * (2 if running else 1)
        step = _v(r, "step_length")
        if isinstance(step, int | float):
            out["stride_length"][i] = step / 1000.0  # mm -> m
    return {k: v for k, v in out.items() if k == "time" or not np.all(np.isnan(v))}
