"""Parsers de GPX y TCX (respaldo para datos antiguos o de otras apps).

Solo aportan lo que el formato trae: tiempo, posición, altitud, distancia, FC y cadencia.
"""

import math
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

import gpxpy
import numpy as np

from app.mapping.fit import ParsedActivity
from app.mapping.streams import FloatArray

EARTH_R = 6_371_000.0


def haversine_cum(lat: FloatArray, lon: FloatArray) -> FloatArray:
    """Distancia acumulada (m) por la fórmula del haversine."""
    la, lo = np.radians(lat), np.radians(lon)
    dla, dlo = np.diff(la), np.diff(lo)
    a = np.sin(dla / 2) ** 2 + np.cos(la[:-1]) * np.cos(la[1:]) * np.sin(dlo / 2) ** 2
    d = 2 * EARTH_R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return np.concatenate([[0.0], np.cumsum(np.nan_to_num(d))])


def _finish(
    times: list[datetime], cols: dict[str, list[float]], sport: str, ext: str
) -> ParsedActivity:
    if len(times) < 2:
        raise ValueError("El archivo no tiene puntos suficientes")
    t0 = times[0] if times[0].tzinfo else times[0].replace(tzinfo=UTC)
    t = np.array([(x.replace(tzinfo=x.tzinfo or UTC) - t0).total_seconds() for x in times])
    streams: dict[str, FloatArray] = {"time": t}
    for k, v in cols.items():
        arr = np.array(v, dtype=float)
        if not np.all(np.isnan(arr)):
            streams[k] = arr
    if "distance" not in streams and "lat" in streams and "lon" in streams:
        streams["distance"] = haversine_cum(streams["lat"], streams["lon"])
    dist = float(np.nanmax(streams["distance"])) if "distance" in streams else None
    duration = float(t[-1])
    hr = streams.get("hr")
    summary: dict[str, Any] = {
        "start_time_utc": t0,
        "sport": sport,
        "distance_m": dist,
        "duration_s": duration,
        "avg_speed": dist / duration if dist and duration else None,
        "avg_hr": float(np.nanmean(hr)) if hr is not None else None,
        "max_hr": float(np.nanmax(hr)) if hr is not None else None,
        "has_streams": True,
    }
    if "altitude" in streams:
        dz = np.diff(streams["altitude"])
        summary["elev_gain_m"] = float(np.nansum(np.where(dz > 0, dz, 0)))
        summary["elev_loss_m"] = float(-np.nansum(np.where(dz < 0, dz, 0)))
    return ParsedActivity(
        summary=summary, streams=streams, external_id=f"{ext}:{int(t0.timestamp())}"
    )


def parse_gpx(data: bytes) -> ParsedActivity:
    gpx = gpxpy.parse(data.decode("utf-8", errors="replace"))
    times: list[datetime] = []
    cols: dict[str, list[float]] = {"lat": [], "lon": [], "altitude": [], "hr": [], "cadence": []}
    sport = "generic"
    for track in gpx.tracks:
        if track.type:
            sport = track.type.lower()
        for seg in track.segments:
            for p in seg.points:
                if p.time is None:
                    continue
                times.append(p.time)
                cols["lat"].append(p.latitude)
                cols["lon"].append(p.longitude)
                cols["altitude"].append(p.elevation if p.elevation is not None else math.nan)
                hr = cad = math.nan
                for ext in p.extensions:
                    for el in ext.iter():
                        tag = el.tag.split("}")[-1].lower()
                        if tag == "hr" and el.text:
                            hr = float(el.text)
                        elif tag in ("cad", "cadence") and el.text:
                            cad = float(el.text)
                cols["hr"].append(hr)
                cols["cadence"].append(cad)
    return _finish(times, cols, sport, "gpx")


def parse_tcx(data: bytes) -> ParsedActivity:
    root = ET.fromstring(data)

    def local(el: ET.Element) -> str:
        return el.tag.split("}")[-1]

    sport = "generic"
    times: list[datetime] = []
    cols: dict[str, list[float]] = {
        "lat": [],
        "lon": [],
        "altitude": [],
        "distance": [],
        "hr": [],
        "cadence": [],
    }
    for el in root.iter():
        if local(el) == "Activity" and el.get("Sport"):
            sport = (el.get("Sport") or "generic").lower()
        if local(el) != "Trackpoint":
            continue
        vals: dict[str, float] = {}
        when: datetime | None = None
        for child in el.iter():
            name, text = local(child), (child.text or "").strip()
            if name == "HeartRateBpm":
                for v in child:
                    if local(v) == "Value" and v.text:
                        vals["hr"] = float(v.text)
                continue
            if not text:
                continue
            if name == "Time":
                when = datetime.fromisoformat(text.replace("Z", "+00:00"))
            elif name == "LatitudeDegrees":
                vals["lat"] = float(text)
            elif name == "LongitudeDegrees":
                vals["lon"] = float(text)
            elif name == "AltitudeMeters":
                vals["altitude"] = float(text)
            elif name == "DistanceMeters":
                vals["distance"] = float(text)
            elif name in ("Cadence", "RunCadence"):
                vals["cadence"] = float(text) * (2 if name == "RunCadence" else 1)
        if when is None:
            continue
        times.append(when)
        for k in cols:
            cols[k].append(vals.get(k, math.nan))
    return _finish(times, cols, sport, "tcx")
