"""Cliente de la Garmin Connect Personal API que implementa `GarminSource`.

- Pausa configurable entre llamadas (0,4 s por defecto).
- Reintentos con backoff exponencial ante 429/5xx/errores de red (respeta Retry-After).
- Ante un 401 renueva el token una vez y repite.
- Cada llamada se notifica a `listener` para el log de sincronización (sin cabeceras).
"""

import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx

from app.sources.base import CallListener, CallRecord, SourceNotConfiguredError
from app.sources.garmin_personal.auth import TokenProvider
from app.sources.garmin_personal.spec import ApiSpec, KindSpec, dig

RETRY_STATUS = {429, 500, 502, 503, 504}


class GarminApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GarminPersonalSource:
    name = "garmin_personal"

    def __init__(
        self,
        spec: ApiSpec,
        tokens: TokenProvider,
        base_url: str,
        *,
        http: httpx.Client | None = None,
        pause_s: float = 0.4,
        max_retries: int = 5,
        listener: CallListener | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.spec = spec
        self.tokens = tokens
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        self.pause_s = pause_s
        self.max_retries = max_retries
        self.listener = listener
        self._sleep = sleep
        self._last_call = 0.0

    # ---- GarminSource -------------------------------------------------------------------

    def range_kinds(self) -> list[str]:
        return [
            name for name, k in self.spec.kinds.items() if name != "activity_file" and k.configured
        ]

    def max_range_days(self, kind: str) -> int:
        return self.spec.kind(kind).max_days

    def fetch_range(self, kind: str, start: date, end: date) -> list[dict[str, Any]]:
        k = self._require(kind)
        params: dict[str, Any] = {
            **k.extra_params,
            k.start_param: k.format_date(start),
            k.end_param: k.format_date(end, end=True),
        }
        if not k.page:
            return self._items(k, self._get_json(kind, k.path, params))
        size = int(k.page["size"])
        offset = int(k.page.get("first", 0))
        out: list[dict[str, Any]] = []
        while True:
            page_params = {**params, k.page["start_param"]: offset, k.page["size_param"]: size}
            items = self._items(k, self._get_json(kind, k.path, page_params))
            out.extend(items)
            if len(items) < size:
                return out
            offset += size

    def record_key(self, kind: str, record: dict[str, Any]) -> str:
        k = self.spec.kind(kind)
        value = dig(record, k.key_field or k.date_field)
        if value is None:
            raise GarminApiError(f"Registro de {kind} sin clave '{k.key_field or k.date_field}'")
        return str(value)

    def activity_file(self, activity_ref: str) -> bytes | None:
        k = self.spec.kind("activity_file")
        if not k.configured:
            return None
        resp = self._request("activity_file", k.path.replace("{id}", activity_ref), {})
        return resp.content

    # ---- HTTP ---------------------------------------------------------------------------

    def _require(self, kind: str) -> KindSpec:
        k = self.spec.kind(kind)
        if not k.configured:
            raise SourceNotConfiguredError(f"'{kind}' no está configurado en endpoints.toml")
        return k

    @staticmethod
    def _items(k: KindSpec, body: Any) -> list[dict[str, Any]]:
        items = dig(body, k.items_path)
        if items is None:
            return []
        if isinstance(items, dict):
            return [items]
        if not isinstance(items, list):
            raise GarminApiError(f"Se esperaba una lista en '{k.items_path or '(raíz)'}'")
        return [i for i in items if isinstance(i, dict)]

    def _get_json(self, kind: str, path: str, params: dict[str, Any]) -> Any:
        resp = self._request(kind, path, params)
        if not resp.content:
            return None
        return resp.json()

    def _throttle(self) -> None:
        wait = self.pause_s - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def _request(self, kind: str, path: str, params: dict[str, Any]) -> httpx.Response:
        url = f"{self.base_url}{path}"
        refreshed = False
        attempt = 0
        while True:
            self._throttle()
            started = time.monotonic()
            record = CallRecord(data_type=kind, method="GET", path=path, params=dict(params))
            try:
                token = self.tokens.get()
                headers = {
                    self.spec.data_auth_header: self.spec.data_auth_template.format(token=token),
                    "Accept": "application/json, application/octet-stream",
                }
                resp = self.http.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                record.status, record.error = "error", f"red: {type(exc).__name__}"
                self._emit(record, started)
                if attempt >= self.max_retries:
                    raise GarminApiError(f"Error de red en {path}: {exc}") from exc
                self._backoff(attempt, None)
                attempt += 1
                continue

            record.http_code = resp.status_code
            if resp.status_code == 401 and not refreshed:
                record.status, record.error = "error", "401: renovando token"
                self._emit(record, started)
                refreshed = True
                self.tokens.get(force_refresh=True)
                continue
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                record.status, record.error = "error", f"HTTP {resp.status_code}: reintento"
                self._emit(record, started)
                self._backoff(attempt, resp.headers.get("Retry-After"))
                attempt += 1
                continue
            if resp.status_code >= 400:
                record.status = "error"
                record.error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                self._emit(record, started)
                raise GarminApiError(record.error, resp.status_code)
            self._emit(record, started)
            return resp

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = min(60.0, 2.0**attempt)
        if retry_after and retry_after.isdigit():
            delay = max(delay, float(retry_after))
        self._sleep(delay)

    def _emit(self, record: CallRecord, started: float) -> None:
        record.duration_ms = (time.monotonic() - started) * 1000
        if self.listener:
            self.listener(record)


def date_chunks(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Trocea [start, end] en rangos de como mucho `max_days` días, del más reciente al más
    antiguo (así lo último aparece antes en la app durante el histórico inicial)."""
    chunks: list[tuple[date, date]] = []
    cur_end = end
    while cur_end >= start:
        cur_start = max(start, cur_end - timedelta(days=max_days - 1))
        chunks.append((cur_start, cur_end))
        cur_end = cur_start - timedelta(days=1)
    return chunks
