from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx

from app.core.logging import redact
from app.sources.base import CallRecord, SourceNotConfiguredError
from app.sources.garmin_personal.auth import (
    AccessToken,
    TokenError,
    TokenProvider,
    parse_token_response,
    request_token,
)
from app.sources.garmin_personal.client import GarminPersonalSource, date_chunks
from app.sources.garmin_personal.spec import ApiSpec, FieldSpec, KindSpec, load_spec

BASE = "https://api.test"
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


def make_spec(**kinds: KindSpec) -> ApiSpec:
    return ApiSpec("Authorization", "Bearer {token}", dict(kinds))


ACTS = KindSpec(
    name="activities",
    path="/acts",
    start_param="from",
    end_param="to",
    max_days=28,
    items_path="data.items",
    key_field="id",
    page={"start_param": "start", "size_param": "limit", "size": 2},
)


def source(spec: ApiSpec, calls: list[CallRecord] | None = None) -> GarminPersonalSource:
    tokens = TokenProvider(fetch=lambda: AccessToken("tok", NOW + timedelta(days=1)))
    return GarminPersonalSource(
        spec,
        tokens,
        BASE,
        pause_s=0,
        sleep=lambda _s: None,
        listener=(calls.append if calls is not None else None),
    )


# ---- token ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected_hours"),
    [
        ({"access_token": "a", "expires_in": 3600}, 1),
        ({"accessToken": "a", "expiresIn": 7200}, 2),
        ({"token": "a"}, 24),
        ("raw-token-string", 24),
    ],
)
def test_parse_token_variants(body: object, expected_hours: int) -> None:
    t = parse_token_response(body, now=NOW)
    assert t.value in ("a", "raw-token-string")
    assert t.expires_at == NOW + timedelta(hours=expected_hours)


def test_parse_token_unknown_shape_shows_keys_not_values() -> None:
    with pytest.raises(TokenError) as e:
        parse_token_response({"weird": "SECRET-VALUE", "n": 1}, now=NOW)
    assert "weird" in str(e.value) and "SECRET-VALUE" not in str(e.value)


@respx.mock
def test_request_token_sends_apikey_header() -> None:
    route = respx.post("https://tok.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "x", "expires_in": 86400})
    )
    t = request_token(httpx.Client(), "https://tok.test/token", "my-key")
    assert t.value == "x"
    assert route.calls[0].request.headers["Authorization"] == "ApiKey my-key"


@respx.mock
def test_request_token_rejected_key() -> None:
    respx.post("https://tok.test/token").mock(return_value=httpx.Response(401))
    with pytest.raises(TokenError, match="rechazó"):
        request_token(httpx.Client(), "https://tok.test/token", "bad")


def test_token_provider_caches_and_stores() -> None:
    fetched: list[int] = []
    stored: list[AccessToken] = []

    def fetch() -> AccessToken:
        fetched.append(1)
        return AccessToken(f"t{len(fetched)}", datetime.now(UTC) + timedelta(hours=24))

    tp = TokenProvider(fetch=fetch, store=stored.append)
    assert tp.get() == "t1" and tp.get() == "t1"
    assert tp.get(force_refresh=True) == "t2"
    assert len(stored) == 2


def test_token_provider_uses_valid_cache() -> None:
    cached = AccessToken("cached", datetime.now(UTC) + timedelta(hours=5))
    tp = TokenProvider(
        fetch=lambda: pytest.fail("no debería pedir token"), load_cached=lambda: cached
    )
    assert tp.get() == "cached"


# ---- cliente --------------------------------------------------------------------------


@respx.mock
def test_fetch_range_paginates_and_formats_dates() -> None:
    route = respx.get(f"{BASE}/acts").mock(
        side_effect=[
            httpx.Response(200, json={"data": {"items": [{"id": 1}, {"id": 2}]}}),
            httpx.Response(200, json={"data": {"items": [{"id": 3}]}}),
        ]
    )
    calls: list[CallRecord] = []
    items = source(make_spec(activities=ACTS), calls).fetch_range(
        "activities", date(2026, 10, 1), date(2026, 10, 7)
    )
    assert [i["id"] for i in items] == [1, 2, 3]
    first = route.calls[0].request
    assert first.url.params["from"] == "2026-10-01" and first.url.params["to"] == "2026-10-07"
    assert first.url.params["start"] == "0" and route.calls[1].request.url.params["start"] == "2"
    assert first.headers["Authorization"] == "Bearer tok"
    assert len(calls) == 2 and all(c.status == "ok" for c in calls)
    assert "Authorization" not in str(calls[0].params)


@respx.mock
def test_retries_on_429_then_succeeds() -> None:
    spec = make_spec(activities=KindSpec("activities", "/acts", "from", "to", key_field="id"))
    respx.get(f"{BASE}/acts").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json=[{"id": 9}]),
        ]
    )
    calls: list[CallRecord] = []
    out = source(spec, calls).fetch_range("activities", date(2026, 1, 1), date(2026, 1, 2))
    assert out == [{"id": 9}]
    assert [c.http_code for c in calls] == [429, 200]


@respx.mock
def test_401_refreshes_token_once() -> None:
    spec = make_spec(activities=KindSpec("activities", "/acts", "from", "to", key_field="id"))
    seq = iter(["old", "new"])
    tp = TokenProvider(fetch=lambda: AccessToken(next(seq), NOW + timedelta(days=9999)))
    src = GarminPersonalSource(spec, tp, BASE, pause_s=0, sleep=lambda _s: None)
    route = respx.get(f"{BASE}/acts").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=[])]
    )
    assert src.fetch_range("activities", date(2026, 1, 1), date(2026, 1, 1)) == []
    assert route.calls[1].request.headers["Authorization"] == "Bearer new"


def test_unconfigured_kind_raises() -> None:
    src = source(make_spec())
    assert src.range_kinds() == []
    with pytest.raises(SourceNotConfiguredError):
        src.fetch_range("sleep", date(2026, 1, 1), date(2026, 1, 2))
    assert src.activity_file("1") is None


def test_date_chunks_newest_first_and_bounded() -> None:
    chunks = date_chunks(date(2026, 1, 1), date(2026, 3, 1), 28)
    assert chunks[0] == (date(2026, 2, 2), date(2026, 3, 1))
    assert chunks[-1][0] == date(2026, 1, 1)
    assert all((b - a).days < 28 for a, b in chunks)
    covered = sum((b - a).days + 1 for a, b in chunks)
    assert covered == (date(2026, 3, 1) - date(2026, 1, 1)).days + 1


def test_epoch_date_formats() -> None:
    k = KindSpec("x", date_format="epoch-ms")
    assert k.format_date(date(1970, 1, 2)) == 86_400_000
    assert KindSpec("x", date_format="epoch-s").format_date(date(1970, 1, 1), end=True) == 86399


def test_shipped_endpoints_toml_loads_and_is_unconfigured() -> None:
    spec = load_spec()
    assert "activities" in spec.kinds
    # Hasta tener el OpenAPI oficial no se activa ningún tipo (nada inventado).
    assert not any(k.configured for k in spec.kinds.values())
    assert isinstance(spec.kind("sleep").fields, dict)
    assert FieldSpec("a").scale == 1.0


def test_redact_hides_secrets() -> None:
    line = 'Authorization: ApiKey abc123 {"access_token": "zzz"} password=hunter2'
    out = redact(line)
    assert "abc123" not in out and "zzz" not in out and "hunter2" not in out
