from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import User, require_cron
from app.core.config import Settings, get_settings
from app.db import get_session, session_scope
from app.models import SyncLog, SyncState
from app.sources.fit_import import import_file
from app.storage import get_storage
from app.sync.factory import GarminNotConnectedError, build_worker
from app.sync.service import active_run_id, plan_run, run_status
from app.sync.summary import build_summary

router = APIRouter(prefix="/api", tags=["sync"])
DbSession = Annotated[Session, Depends(get_session)]

MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # Vercel limita el cuerpo a 4,5 MB


class SyncStarted(BaseModel):
    run_id: str
    status: dict[str, Any]


def _start_and_tick(settings: Settings, budget_s: float, full: bool = False) -> SyncStarted:
    try:
        worker, source = build_worker(settings)
    except GarminNotConnectedError as exc:
        raise HTTPException(503, str(exc)) from exc
    with session_scope() as s:
        run_id = plan_run(
            s,
            source,
            date.today(),
            initial_days=settings.sync_initial_days,
            resync_days=settings.sync_resync_daily_days,
            full=full,
        )
    worker.tick(budget_s=budget_s)
    with session_scope() as s:
        return SyncStarted(run_id=run_id, status=run_status(s, run_id))


@router.post("/sync", response_model=SyncStarted)
def start_sync(
    _user: User, full: bool = False, settings: Settings = Depends(get_settings)
) -> SyncStarted:
    """Crea (o continúa) una ejecución y avanza lo que quepa en el presupuesto de tiempo.
    El resto lo completa pg_cron, o la propia UI llamando a /api/sync/continue."""
    return _start_and_tick(settings, settings.sync_tick_budget_s, full)


@router.post("/sync/continue")
def continue_sync(_user: User, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        worker, _ = build_worker(settings)
    except GarminNotConnectedError as exc:
        raise HTTPException(503, str(exc)) from exc
    res = worker.tick(budget_s=settings.sync_tick_budget_s)
    return {"processed": res.processed, "failed": res.failed, "remaining": res.remaining}


@router.api_route("/sync/tick", methods=["GET", "POST"], dependencies=[Depends(require_cron)])
def cron_tick(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Llamado por pg_cron (cabecera X-Cron-Secret) cada pocos minutos.
    Avanza la cola si hay trabajo pendiente; si no, y han pasado SYNC_AUTO_INTERVAL_H horas
    desde la última sincronización, planifica una incremental."""
    with session_scope() as s:
        running = active_run_id(s) is not None
        last = s.scalar(select(func.max(SyncState.last_run_at)))
    if not running:
        if settings.sync_auto_interval_h <= 0:
            return {"skipped": "auto-sync desactivada"}
        if last is not None:
            last = last if last.tzinfo else last.replace(tzinfo=UTC)
            if datetime.now(UTC) - last < timedelta(hours=settings.sync_auto_interval_h):
                return {"skipped": "aún no toca"}
    started = _start_and_tick(settings, settings.sync_tick_budget_s)
    return {"run_id": started.run_id, "progress": started.status["progress"]}


@router.get("/sync/status")
def sync_status(_user: User, s: DbSession, run_id: str | None = None) -> dict[str, Any]:
    rid = run_id or active_run_id(s)
    if rid is None:
        return {"run_id": None, "finished": True, "progress": 1.0}
    return run_status(s, rid)


@router.get("/sync/summary")
def sync_summary(_user: User, s: DbSession) -> dict[str, Any]:
    return build_summary(s)


@router.get("/sync/log")
def sync_log(
    _user: User, s: DbSession, limit: int = Query(100, le=500), only_errors: bool = False
) -> list[dict[str, Any]]:
    q = select(SyncLog).order_by(SyncLog.at.desc()).limit(limit)
    if only_errors:
        q = q.where(SyncLog.status == "error")
    return [
        {
            "at": r.at.isoformat(),
            "run_id": r.run_id,
            "data_type": r.data_type,
            "method": r.method,
            "path": r.path,
            "params": r.params_json,
            "status": r.status,
            "http_code": r.http_code,
            "items": r.items,
            "error": r.error,
            "duration_ms": r.duration_ms,
        }
        for r in s.scalars(q)
    ]


@router.post("/import")
async def import_upload(_user: User, file: UploadFile, s: DbSession) -> dict[str, Any]:
    """Importación de archivos pequeños (≤ 4 MB). Los exports grandes van por `make import`."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Archivo demasiado grande para la web: usa `make import`")
    rep = import_file(s, get_storage(), file.filename or "upload.fit", data)
    return {
        "created": rep.created,
        "updated": rep.updated,
        "skipped": rep.skipped,
        "errors": rep.errors,
    }
