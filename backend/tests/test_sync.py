import io
import zipfile
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.mapping.fit import parse_fit
from app.mapping.persist import upsert_activity
from app.models import (
    Activity,
    ActivityStream,
    DailyMetrics,
    Lap,
    RawDocument,
    SyncJob,
    SyncLog,
    SyncState,
)
from app.sources.base import CallRecord
from app.sources.fit_import import import_file
from app.sources.garmin_personal.spec import ApiSpec, FieldSpec, KindSpec
from app.storage import LocalStorage
from app.sync.service import SyncWorker, plan_run, run_status
from app.sync.summary import build_summary, format_summary
from tests.fixtures.fit_builder import START, build_run_fit, build_swim_fit

TODAY = date(2026, 10, 26)

SPEC = ApiSpec(
    "Authorization",
    "Bearer {token}",
    {
        "activities": KindSpec("activities", "/a", "s", "e", max_days=28, key_field="activityId"),
        "activity_file": KindSpec("activity_file", "/f/{id}"),
        "sleep": KindSpec(
            "sleep",
            "/sleep",
            "s",
            "e",
            max_days=31,
            date_field="calendarDate",
            fields={
                "sleep_total_s": FieldSpec("dur"),
                "sleep_score": FieldSpec("scores.overall"),
                "hrv_night_avg": FieldSpec("hrv_ms", scale=1.0),
            },
        ),
    },
)


class FakeSource:
    """Fuente simulada con la interfaz de GarminSource; registra lo que se le pide."""

    name = "garmin_personal"

    def __init__(self, calls: list[CallRecord]) -> None:
        self.calls = calls
        self.requests: list[tuple[str, date, date]] = []
        self.fit = build_run_fit()

    def range_kinds(self) -> list[str]:
        return ["activities", "sleep"]

    def max_range_days(self, kind: str) -> int:
        return SPEC.kind(kind).max_days

    def fetch_range(self, kind: str, start: date, end: date) -> list[dict[str, Any]]:
        self.requests.append((kind, start, end))
        self.calls.append(CallRecord(kind, "GET", f"/{kind}"))
        if kind == "activities" and start <= START.date() <= end:
            return [{"activityId": 555}]
        if kind == "sleep" and start <= TODAY <= end:
            return [{"calendarDate": TODAY.isoformat(), "dur": 27000, "scores": {"overall": 81}}]
        return []

    def record_key(self, kind: str, record: dict[str, Any]) -> str:
        return str(record.get("activityId") or record.get("calendarDate"))

    def activity_file(self, activity_ref: str) -> bytes | None:
        self.calls.append(CallRecord("activity_file", "GET", f"/f/{activity_ref}"))
        return self.fit


def make_worker(
    sf: sessionmaker[Session], tmp_storage: LocalStorage
) -> tuple[SyncWorker, FakeSource]:
    calls: list[CallRecord] = []
    src = FakeSource(calls)
    return SyncWorker(sf, src, tmp_storage, SPEC, calls), src


def test_initial_sync_end_to_end(sf: sessionmaker[Session], tmp_path: Any) -> None:
    storage = LocalStorage(tmp_path / "files")
    worker, src = make_worker(sf, storage)
    with sf.begin() as s:
        run_id = plan_run(s, src, TODAY, initial_days=365, resync_days=3)
    with sf() as s:
        jobs = s.scalars(select(SyncJob).where(SyncJob.run_id == run_id)).all()
        assert {j.data_type for j in jobs} == {"activities", "sleep"}
        # 365 días en trozos de 28 y 31 días
        assert sum(j.data_type == "activities" for j in jobs) == 14
        assert sum(j.data_type == "sleep" for j in jobs) == 12

    res = worker.tick(budget_s=60)
    assert res.failed == 0 and res.remaining == 0

    with sf() as s:
        st = run_status(s, run_id)
        assert st["finished"] and st["by_kind"]["activity_file"]["done"] == 1
        act = s.scalar(select(Activity))
        assert act is not None
        assert act.external_id == "555" and act.source == "garmin_personal"
        assert act.fit_storage_key == "garmin/555.fit" and storage.get("garmin/555.fit")
        assert s.scalar(select(func.count()).select_from(Lap)) == 2
        assert s.get(ActivityStream, act.id) is not None
        day = s.get(DailyMetrics, TODAY)
        assert day is not None and day.sleep_total_s == 27000 and day.sleep_score == 81
        assert day.hrv_night_avg is None  # no viene en el registro -> "sin datos"
        assert s.scalar(select(func.count()).select_from(RawDocument)) == 2
        assert s.scalar(select(func.count()).select_from(SyncLog)) >= 27
        state = s.get(SyncState, "sleep")
        assert state is not None and state.synced_until == TODAY

        summary = build_summary(s, SPEC)
        assert summary["activities"]["total"] == 1
        assert "sleep_total_s" in summary["daily"]["arriving"]
        assert "hrv_night_avg" in summary["daily"]["missing"]
        assert "Actividades: 1" in format_summary(summary)


def test_incremental_sync_resyncs_last_days(sf: sessionmaker[Session], tmp_path: Any) -> None:
    worker, src = make_worker(sf, LocalStorage(tmp_path / "files"))
    with sf.begin() as s:
        plan_run(s, src, TODAY, initial_days=30, resync_days=3)
    worker.tick(budget_s=60)
    src.requests.clear()
    later = TODAY + timedelta(days=2)
    with sf.begin() as s:
        plan_run(s, src, later, initial_days=30, resync_days=3)
    worker.tick(budget_s=60)
    sleep_reqs = [(a, b) for k, a, b in src.requests if k == "sleep"]
    act_reqs = [(a, b) for k, a, b in src.requests if k == "activities"]
    assert sleep_reqs == [(TODAY - timedelta(days=3), later)]
    assert act_reqs == [(TODAY - timedelta(days=1), later)]


def test_plan_reuses_active_run(sf: sessionmaker[Session], tmp_path: Any) -> None:
    _, src = make_worker(sf, LocalStorage(tmp_path / "files"))
    with sf.begin() as s:
        a = plan_run(s, src, TODAY, initial_days=10, resync_days=3)
        b = plan_run(s, src, TODAY, initial_days=10, resync_days=3)
    assert a == b


def test_failing_job_retries_then_errors(sf: sessionmaker[Session], tmp_path: Any) -> None:
    worker, src = make_worker(sf, LocalStorage(tmp_path / "files"))

    def boom(kind: str, start: date, end: date) -> list[dict[str, Any]]:
        raise RuntimeError("Garmin caído")

    src.fetch_range = boom  # type: ignore[method-assign]
    with sf.begin() as s:
        run_id = plan_run(s, src, TODAY, initial_days=5, resync_days=3)
    res = worker.tick(budget_s=60)
    assert res.remaining == 0 and res.failed == 6  # 2 trabajos x 3 intentos
    with sf() as s:
        st = run_status(s, run_id)
        assert st["by_kind"]["sleep"]["error"] == 1
        assert any("Garmin caído" in e for e in st["errors"])


def test_manual_fields_survive_resync(session: Session) -> None:
    parsed = parse_fit(build_run_fit())
    act, created = upsert_activity(session, parsed, source="garmin_personal", external_id="1")
    assert created
    act.rpe, act.notes, act.is_race = 7, "piernas cargadas", True
    session.flush()
    parsed.summary["avg_hr"] = 155
    act2, created2 = upsert_activity(session, parsed, source="garmin_personal", external_id="1")
    assert not created2 and act2.id == act.id
    assert (act2.rpe, act2.notes, act2.is_race, act2.avg_hr) == (7, "piernas cargadas", True, 155)


def test_import_dedupes_against_synced_activity(session: Session, tmp_path: Any) -> None:
    data = build_run_fit()
    upsert_activity(session, parse_fit(data), source="garmin_personal", external_id="555")
    rep = import_file(session, LocalStorage(tmp_path / "f"), "run.fit", data)
    assert (rep.created, rep.updated) == (0, 1)
    assert session.scalar(select(func.count()).select_from(Activity)) == 1


def test_import_nested_zip_export(session: Session, tmp_path: Any) -> None:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("a/run.fit", build_run_fit())
        z.writestr("a/swim.fit", build_swim_fit(start=START + timedelta(days=1)))
        z.writestr("a/broken.fit", b"basura")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("DI_CONNECT/UploadedFiles_0-_Part1.zip", inner.getvalue())
        z.writestr("DI_CONNECT/profile.json", "{}")
    rep = import_file(session, LocalStorage(tmp_path / "f"), "export.zip", outer.getvalue())
    assert rep.created == 2
    assert rep.skipped + len(rep.errors) == 1
    sports = set(session.scalars(select(Activity.sport)))
    assert sports == {"running", "swimming"}
