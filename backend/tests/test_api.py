import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from tests.fixtures.fit_builder import build_run_fit


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] and body["garmin_key_configured"]


def test_import_and_summary(client: TestClient) -> None:
    r = client.post(
        "/api/import", files={"file": ("run.fit", build_run_fit(), "application/octet-stream")}
    )
    assert r.status_code == 200 and r.json()["created"] == 1
    s = client.get("/api/sync/summary").json()
    assert s["activities"]["total"] == 1
    assert s["activities"]["by_sport"][0]["sport"] == "running"


def test_import_rejects_big_file(client: TestClient) -> None:
    big = b"0" * (4 * 1024 * 1024 + 10)
    assert client.post("/api/import", files={"file": ("x.fit", big)}).status_code == 413


def test_cron_requires_secret(client: TestClient) -> None:
    assert client.post("/api/sync/tick").status_code == 401
    assert client.post("/api/sync/tick", headers={"X-Cron-Secret": "mal"}).status_code == 401


def test_cron_with_unconfigured_garmin_is_harmless(client: TestClient) -> None:
    r = client.post("/api/sync/tick", headers={"X-Cron-Secret": "test-cron"})
    assert r.status_code == 200
    assert client.get("/api/sync/status").json()["finished"] is True


def test_sync_status_idle(client: TestClient) -> None:
    assert client.get("/api/sync/status").json() == {
        "run_id": None,
        "finished": True,
        "progress": 1.0,
    }


def test_auth_required_when_enabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("ALLOWED_EMAIL", "adrian@example.com")
    get_settings.cache_clear()
    assert client.get("/api/sync/summary").status_code == 401
    r = client.get("/api/sync/summary", headers={"Authorization": "Bearer no.es.jwt"})
    assert r.status_code == 401


def test_jwt_hs256_allowed_email(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import jwt

    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("ALLOWED_EMAIL", "Adrian@Example.com")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "s" * 32)
    get_settings.cache_clear()

    def tok(email: str) -> str:
        return jwt.encode({"email": email, "aud": "authenticated"}, "s" * 32, algorithm="HS256")

    ok = client.get("/api/me", headers={"Authorization": f"Bearer {tok('adrian@example.com')}"})
    assert ok.status_code == 200
    other = client.get("/api/me", headers={"Authorization": f"Bearer {tok('otro@x.com')}"})
    assert other.status_code == 403
