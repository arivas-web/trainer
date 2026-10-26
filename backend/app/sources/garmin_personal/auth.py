"""Canje de la clave API personal por un access token (válido ~24 h, sin refresh token).

Endpoint confirmado: POST {GARMIN_TOKEN_URL} con `Authorization: ApiKey <clave>`.
La forma de la respuesta aún no está verificada: aceptamos los nombres habituales de OAuth2
y, si no encajan, fallamos mostrando SOLO los nombres de los campos (nunca los valores).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

TOKEN_KEYS = ("access_token", "accessToken", "token")
EXPIRES_IN_KEYS = ("expires_in", "expiresIn", "expiresInSeconds")
EXPIRES_AT_KEYS = ("expires_at", "expiresAt", "expiration", "expirationTime")
DEFAULT_LIFETIME = timedelta(hours=24)
SAFETY_MARGIN = timedelta(minutes=10)


class TokenError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_at: datetime

    def valid(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return now < self.expires_at - SAFETY_MARGIN


def _parse_expiry(body: dict[str, Any], now: datetime) -> datetime:
    for k in EXPIRES_IN_KEYS:
        if isinstance(body.get(k), int | float):
            return now + timedelta(seconds=float(body[k]))
    for k in EXPIRES_AT_KEYS:
        v = body.get(k)
        if isinstance(v, int | float):  # epoch (s o ms)
            ts = v / 1000 if v > 10**11 else v
            return datetime.fromtimestamp(ts, UTC)
        if isinstance(v, str):
            try:
                parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
    return now + DEFAULT_LIFETIME


def parse_token_response(body: Any, now: datetime | None = None) -> AccessToken:
    now = now or datetime.now(UTC)
    if isinstance(body, str) and body.strip():
        return AccessToken(body.strip(), now + DEFAULT_LIFETIME)
    if not isinstance(body, dict):
        raise TokenError(f"Respuesta de token inesperada (tipo {type(body).__name__})")
    for k in TOKEN_KEYS:
        if isinstance(body.get(k), str) and body[k]:
            return AccessToken(body[k], _parse_expiry(body, now))
    shape = {k: type(v).__name__ for k, v in body.items()}
    raise TokenError(f"No encuentro el token en la respuesta. Campos recibidos: {shape}")


def request_token(client: httpx.Client, token_url: str, api_key: str) -> AccessToken:
    resp = client.post(token_url, headers={"Authorization": f"ApiKey {api_key}"})
    if resp.status_code in (401, 403):
        raise TokenError(
            f"Garmin rechazó la clave API personal (HTTP {resp.status_code}). "
            "¿Ha caducado o se ha regenerado?"
        )
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    body: Any = resp.json() if "json" in ctype else resp.text
    return parse_token_response(body)


class TokenProvider:
    """Mantiene un token válido, con caché opcional (p. ej. en la base de datos, cifrado)."""

    def __init__(
        self,
        fetch: Callable[[], AccessToken],
        load_cached: Callable[[], AccessToken | None] = lambda: None,
        store: Callable[[AccessToken], None] = lambda _t: None,
    ) -> None:
        self._fetch = fetch
        self._load_cached = load_cached
        self._store = store
        self._token: AccessToken | None = None

    def get(self, force_refresh: bool = False) -> str:
        if not force_refresh:
            if self._token is None:
                self._token = self._load_cached()
            if self._token is not None and self._token.valid():
                return self._token.value
        self._token = self._fetch()
        self._store(self._token)
        return self._token.value
