"""Resumen de lo descargado: actividades por deporte, rango de fechas y qué métricas diarias
llegan y cuáles no. Es lo que Adrián revisa en el checkpoint de la Fase 1."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Activity, ActivityStream, DailyMetrics, RawDocument, SyncJob, SyncLog
from app.sources.garmin_personal.spec import ApiSpec, load_spec

DAILY_FIELDS = [
    c
    for c in (col.name for col in DailyMetrics.__table__.columns)
    if c not in ("date", "updated_at")
]


def build_summary(session: Session, spec: ApiSpec | None = None) -> dict[str, Any]:
    spec = spec or load_spec()
    by_sport = session.execute(
        select(
            Activity.sport,
            Activity.sub_sport,
            func.count(),
            func.sum(Activity.distance_m),
            func.sum(Activity.duration_s),
        )
        .group_by(Activity.sport, Activity.sub_sport)
        .order_by(func.count().desc())
    ).all()
    first, last, n = session.execute(
        select(func.min(Activity.start_time_utc), func.max(Activity.start_time_utc), func.count())
    ).one()
    flags = session.execute(
        select(
            func.count().filter(Activity.has_streams.is_(True)),
            func.count().filter(Activity.has_power.is_(True)),
            func.count().filter(Activity.has_running_dynamics.is_(True)),
            func.count().filter(Activity.avg_hr.is_not(None)),
            func.count().filter(Activity.fit_storage_key.is_not(None)),
        )
    ).one()
    by_source = dict(
        session.execute(select(Activity.source, func.count()).group_by(Activity.source)).all()
    )
    n_streams = session.scalar(select(func.count()).select_from(ActivityStream)) or 0

    d_first, d_last, d_n = session.execute(
        select(func.min(DailyMetrics.date), func.max(DailyMetrics.date), func.count())
    ).one()
    daily_coverage: dict[str, int] = {}
    if d_n:
        counts = session.execute(
            select(*[func.count(getattr(DailyMetrics, c)) for c in DAILY_FIELDS])
        ).one()
        daily_coverage = dict(zip(DAILY_FIELDS, (int(x) for x in counts), strict=True))

    raw = dict(
        session.execute(select(RawDocument.kind, func.count()).group_by(RawDocument.kind)).all()
    )
    jobs = session.execute(select(SyncJob.status, func.count()).group_by(SyncJob.status)).all()
    recent_errors = session.execute(
        select(SyncLog.at, SyncLog.data_type, SyncLog.path, SyncLog.http_code, SyncLog.error)
        .where(SyncLog.status == "error")
        .order_by(SyncLog.at.desc())
        .limit(10)
    ).all()

    return {
        "activities": {
            "total": n,
            "first": first.isoformat() if first else None,
            "last": last.isoformat() if last else None,
            "by_sport": [
                {
                    "sport": sp,
                    "sub_sport": sub,
                    "count": c,
                    "km": round((dist or 0) / 1000, 1),
                    "hours": round((dur or 0) / 3600, 1),
                }
                for sp, sub, c, dist, dur in by_sport
            ],
            "by_source": by_source,
            "with_streams": flags[0],
            "with_power": flags[1],
            "with_running_dynamics": flags[2],
            "with_hr": flags[3],
            "with_fit": flags[4],
            "stream_rows": n_streams,
        },
        "daily": {
            "days": d_n,
            "first": d_first.isoformat() if d_first else None,
            "last": d_last.isoformat() if d_last else None,
            "coverage": daily_coverage,
            "arriving": sorted(k for k, v in daily_coverage.items() if v > 0),
            "missing": sorted(k for k, v in daily_coverage.items() if v == 0)
            if d_n
            else DAILY_FIELDS,
        },
        "garmin_kinds": {
            name: {"configured": k.configured, "raw_records": raw.get(name, 0)}
            for name, k in sorted(spec.kinds.items())
        },
        "jobs": dict(jobs),
        "recent_errors": [
            {"at": at.isoformat(), "kind": kind, "path": path, "http": code, "error": err}
            for at, kind, path, code, err in recent_errors
        ],
    }


def format_summary(s: dict[str, Any]) -> str:
    """Versión de consola del resumen."""
    a, d = s["activities"], s["daily"]
    lines = ["", "══ PULSE · resumen de datos ══", ""]
    lines.append(f"Actividades: {a['total']}  ({a['first'] or '—'} → {a['last'] or '—'})")
    for row in a["by_sport"]:
        sub = f"/{row['sub_sport']}" if row["sub_sport"] else ""
        label = f"{row['sport']}{sub}"
        lines.append(f"  · {label:<26} {row['count']:>4}  {row['km']:>8} km  {row['hours']:>6} h")
    lines.append(
        f"  con streams {a['with_streams']} · con FC {a['with_hr']} · con potencia "
        f"{a['with_power']} · con dinámica de carrera {a['with_running_dynamics']} · "
        f"con FIT {a['with_fit']}"
    )
    lines.append(f"  por origen: {a['by_source'] or '—'}")
    lines.append("")
    lines.append(f"Métricas diarias: {d['days']} días ({d['first'] or '—'} → {d['last'] or '—'})")
    if d["days"]:
        for k, v in d["coverage"].items():
            mark = "✓" if v else "✗"
            lines.append(f"  {mark} {k:<24} {v:>4}/{d['days']}")
    else:
        lines.append("  (ninguna todavía)")
    lines.append("")
    lines.append("Tipos de Garmin:")
    for name, info in s["garmin_kinds"].items():
        state = "configurado" if info["configured"] else "NO configurado (falta OpenAPI)"
        lines.append(f"  · {name:<18} {state:<32} registros crudos: {info['raw_records']}")
    if s["jobs"]:
        lines.append("")
        lines.append(f"Trabajos de sync: {s['jobs']}")
    if s["recent_errors"]:
        lines.append("")
        lines.append("Últimos errores:")
        for e in s["recent_errors"]:
            lines.append(f"  {e['at'][:19]} {e['kind']} {e['path']} HTTP {e['http']}: {e['error']}")
    return "\n".join(lines)
