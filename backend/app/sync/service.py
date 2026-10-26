"""Orquestador de sincronización incremental basado en una cola de trabajos (`sync_jobs`).

- `plan_run` crea trozos de ≤ max_days por tipo de dato, del más reciente al más antiguo.
  Primera vez: `initial_days` hacia atrás. Después: desde el último día sincronizado,
  re-pidiendo siempre los últimos `resync_days` de métricas diarias (Garmin las corrige).
- `tick` procesa trabajos pendientes hasta agotar el presupuesto de tiempo (pensado para
  funciones serverless: cada llamada de pg_cron o del botón avanza un poco).
- Cada llamada HTTP queda en `sync_log`.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.mapping.daily import map_daily_record, record_date, upsert_daily
from app.mapping.fit import parse_fit
from app.mapping.persist import sha256, upsert_activity
from app.models import Activity, RawDocument, SyncJob, SyncLog, SyncState
from app.sources.base import CallRecord, GarminSource
from app.sources.garmin_personal.client import date_chunks
from app.sources.garmin_personal.spec import DAILY_KINDS, ApiSpec
from app.storage import FileStorage

log = logging.getLogger(__name__)

ACTIVITY_FILE = "activity_file"
MAX_ATTEMPTS = 3
PRIORITY = {"activities": 10, ACTIVITY_FILE: 15}
DEFAULT_PRIORITY = 20


def _now() -> datetime:
    return datetime.now(UTC)


def active_run_id(session: Session) -> str | None:
    return session.scalar(
        select(SyncJob.run_id)
        .where(SyncJob.status.in_(("pending", "running")))
        .order_by(SyncJob.id)
        .limit(1)
    )


def plan_run(
    session: Session,
    source: GarminSource,
    today: date,
    *,
    initial_days: int,
    resync_days: int,
    full: bool = False,
) -> str:
    """Crea los trabajos de una ejecución. Si ya hay una en curso, devuelve su run_id."""
    existing = active_run_id(session)
    if existing:
        return existing
    run_id = str(uuid.uuid4())
    for kind in source.range_kinds():
        state = session.get(SyncState, kind)
        if state and state.synced_until and not full:
            back = resync_days if kind in DAILY_KINDS else 1
            start = min(state.synced_until, today) - timedelta(days=back)
        else:
            start = today - timedelta(days=initial_days)
        for a, b in date_chunks(start, today, source.max_range_days(kind)):
            session.add(
                SyncJob(
                    run_id=run_id,
                    data_type=kind,
                    range_start=a,
                    range_end=b,
                    priority=PRIORITY.get(kind, DEFAULT_PRIORITY),
                )
            )
    session.flush()
    return run_id


@dataclass
class TickResult:
    processed: int = 0
    failed: int = 0
    remaining: int = 0
    run_id: str | None = None
    errors: list[str] = field(default_factory=list)


class SyncWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        source: GarminSource,
        storage: FileStorage,
        spec: ApiSpec,
        call_buffer: list[CallRecord],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sf = session_factory
        self.source = source
        self.storage = storage
        self.spec = spec
        self.calls = call_buffer  # el listener del cliente HTTP escribe aquí
        self.clock = clock

    def tick(self, budget_s: float) -> TickResult:
        deadline = self.clock() + budget_s
        result = TickResult()
        while self.clock() < deadline:
            job_id = self._claim()
            if job_id is None:
                break
            ok, err = self._run(job_id)
            result.processed += 1
            if not ok:
                result.failed += 1
                result.errors.append(err or "error")
        with self.sf() as s:
            result.remaining = (
                s.scalar(
                    select(func.count()).select_from(SyncJob).where(SyncJob.status == "pending")
                )
                or 0
            )
            result.run_id = active_run_id(s)
        return result

    def _claim(self) -> int | None:
        with self.sf.begin() as s:
            q = (
                select(SyncJob)
                .where(SyncJob.status == "pending")
                .order_by(SyncJob.priority, SyncJob.id)
                .limit(1)
            )
            if s.bind is not None and s.bind.dialect.name == "postgresql":
                q = q.with_for_update(skip_locked=True)
            job = s.scalar(q)
            if job is None:
                return None
            job.status = "running"
            job.attempts += 1
            return job.id

    def _run(self, job_id: int) -> tuple[bool, str | None]:
        self.calls.clear()
        error: str | None = None
        try:
            with self.sf.begin() as s:
                job = s.get_one(SyncJob, job_id)
                job.items = self._process(s, job)
                job.status, job.finished_at, job.error = "done", _now(), None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.warning("Trabajo %s falló: %s", job_id, error)
            with self.sf.begin() as s:
                job = s.get_one(SyncJob, job_id)
                job.error = error[:2000]
                job.status = "pending" if job.attempts < MAX_ATTEMPTS else "error"
                if job.status == "error":
                    job.finished_at = _now()
        self._flush_log(job_id)
        return error is None, error

    def _flush_log(self, job_id: int) -> None:
        if not self.calls:
            return
        with self.sf.begin() as s:
            run_id = s.get_one(SyncJob, job_id).run_id
            for c in self.calls:
                s.add(
                    SyncLog(
                        run_id=run_id,
                        data_type=c.data_type,
                        method=c.method,
                        path=c.path,
                        params_json={k: str(v) for k, v in c.params.items()},
                        status=c.status,
                        http_code=c.http_code,
                        items=c.items,
                        error=c.error,
                        duration_ms=c.duration_ms,
                    )
                )
        self.calls.clear()

    # ---- procesado por tipo -------------------------------------------------------------

    def _process(self, s: Session, job: SyncJob) -> int:
        if job.data_type == ACTIVITY_FILE:
            return self._process_activity_file(s, job)
        assert job.range_start and job.range_end
        records = self.source.fetch_range(job.data_type, job.range_start, job.range_end)
        if self.calls:
            self.calls[-1].items = len(records)
        for rec in records:
            key = self.source.record_key(job.data_type, rec)
            self._save_raw(s, job.data_type, key, rec)
            if job.data_type == "activities":
                self._maybe_enqueue_file(s, job, key)
            elif job.data_type in DAILY_KINDS:
                kind = self.spec.kind(job.data_type)
                day = record_date(kind, rec)
                if day is not None:
                    upsert_daily(s, day, map_daily_record(kind, rec))
        self._advance_state(s, job.data_type, job.range_start, job.range_end)
        return len(records)

    def _process_activity_file(self, s: Session, job: SyncJob) -> int:
        assert job.ref
        data = self.source.activity_file(job.ref)
        if not data:
            return 0
        key = f"garmin/{job.ref}.fit"
        self.storage.put(key, data)
        parsed = parse_fit(data)
        upsert_activity(
            s,
            parsed,
            source=self.source.name,
            external_id=job.ref,
            file_bytes=data,
            storage_key=key,
        )
        log.debug("FIT %s (%s)", job.ref, sha256(data)[:8])
        return 1

    def _maybe_enqueue_file(self, s: Session, job: SyncJob, ref: str) -> None:
        if not self.spec.kind(ACTIVITY_FILE).configured:
            return
        have = s.scalar(
            select(Activity.id).where(
                Activity.source == self.source.name,
                Activity.external_id == ref,
                Activity.fit_storage_key.is_not(None),
            )
        )
        queued = s.scalar(
            select(SyncJob.id).where(
                SyncJob.data_type == ACTIVITY_FILE,
                SyncJob.ref == ref,
                SyncJob.status.in_(("pending", "running")),
            )
        )
        if have is None and queued is None:
            s.add(
                SyncJob(
                    run_id=job.run_id,
                    data_type=ACTIVITY_FILE,
                    ref=ref,
                    priority=PRIORITY[ACTIVITY_FILE],
                )
            )

    @staticmethod
    def _save_raw(s: Session, kind: str, key: str, payload: Any) -> None:
        doc = s.scalar(select(RawDocument).where(RawDocument.kind == kind, RawDocument.key == key))
        if doc is None:
            s.add(RawDocument(kind=kind, key=key, payload=payload))
        else:
            doc.payload, doc.fetched_at = payload, _now()

    @staticmethod
    def _advance_state(s: Session, kind: str, start: date, end: date) -> None:
        st = s.get(SyncState, kind)
        if st is None:
            st = SyncState(data_type=kind)
            s.add(st)
        st.synced_until = max(filter(None, (st.synced_until, end)))
        st.oldest_synced = min(filter(None, (st.oldest_synced, start)))
        st.last_run_at = _now()


def run_status(session: Session, run_id: str) -> dict[str, Any]:
    rows = session.execute(
        select(SyncJob.data_type, SyncJob.status, func.count(), func.sum(SyncJob.items))
        .where(SyncJob.run_id == run_id)
        .group_by(SyncJob.data_type, SyncJob.status)
    ).all()
    by_kind: dict[str, dict[str, int]] = {}
    total = done = 0
    for kind, status, n, items in rows:
        k = by_kind.setdefault(
            kind, {"pending": 0, "running": 0, "done": 0, "error": 0, "items": 0}
        )
        k[status] = n
        k["items"] += int(items or 0)
        total += n
        if status in ("done", "error"):
            done += n
    errors = session.scalars(
        select(SyncJob.error).where(SyncJob.run_id == run_id, SyncJob.error.is_not(None)).limit(10)
    ).all()
    return {
        "run_id": run_id,
        "total_jobs": total,
        "finished_jobs": done,
        "progress": (done / total) if total else 1.0,
        "finished": total == done,
        "by_kind": by_kind,
        "errors": list(errors),
    }
