"""Autenticación: JWT de Supabase Auth + lista blanca de un único email.

Admite las dos formas de firma de Supabase:
- claves asimétricas (JWKS en {SUPABASE_URL}/auth/v1/.well-known/jwks.json), las de los
  proyectos nuevos;
- secreto HS256 compartido (SUPABASE_JWT_SECRET), el de los proyectos antiguos.
"""

import hmac
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")
    if alg == "HS256":
        if settings.supabase_jwt_secret is None:
            raise jwt.InvalidTokenError("Token HS256 pero falta SUPABASE_JWT_SECRET")
        key: Any = settings.supabase_jwt_secret.get_secret_value()
    else:
        if not settings.supabase_url:
            raise jwt.InvalidTokenError("Falta SUPABASE_URL para validar el token")
        key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
    claims: dict[str, Any] = jwt.decode(
        token, key, algorithms=["HS256", "RS256", "ES256"], audience="authenticated"
    )
    return claims


def require_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if settings.auth_disabled:
        return {"email": settings.allowed_email or "dev@local", "dev": True}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token de sesión")
    try:
        claims = decode_token(authorization.split(" ", 1)[1], settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no válida") from exc
    email = str(claims.get("email", "")).lower()
    if not settings.allowed_email or email != settings.allowed_email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario no autorizado")
    return claims


def require_cron(
    x_cron_secret: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """pg_cron envía `X-Cron-Secret`; Vercel Cron envía `Authorization: Bearer <CRON_SECRET>`."""
    expected = settings.cron_secret.get_secret_value() if settings.cron_secret else None
    given = x_cron_secret
    if given is None and authorization and authorization.lower().startswith("bearer "):
        given = authorization.split(" ", 1)[1]
    if not expected or not given or not hmac.compare_digest(given, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Secreto de cron no válido")


User = Annotated[dict[str, Any], Depends(require_user)]
