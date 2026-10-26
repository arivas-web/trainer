from typing import Any

import httpx
from fastapi import APIRouter, Depends

from app.core.auth import User
from app.core.config import Settings, get_settings
from app.sources.garmin_personal.auth import TokenError, parse_token_response
from app.sources.garmin_personal.probe import shape

router = APIRouter(prefix="/api/garmin", tags=["garmin"])


@router.get("/check")
def check_connection(_user: User, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Canjea la clave por un token y devuelve si ha funcionado y la FORMA de la respuesta
    (nombres de campos y tipos), nunca el token ni la clave."""
    key = settings.garmin_personal_api_key
    if key is None:
        return {"ok": False, "step": "config", "error": "Falta GARMIN_PERSONAL_API_KEY en Vercel"}
    try:
        resp = httpx.post(
            settings.garmin_token_url,
            headers={"Authorization": f"ApiKey {key.get_secret_value()}"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "step": "network", "error": f"{type(exc).__name__}: {exc}"}
    ctype = resp.headers.get("content-type", "")
    try:
        body: Any = resp.json() if "json" in ctype else resp.text
    except ValueError:
        body = resp.text
    result: dict[str, Any] = {
        "http_status": resp.status_code,
        "content_type": ctype,
        "response_shape": shape(body) if not isinstance(body, str) else f"texto ({len(body)} car.)",
    }
    if resp.status_code >= 400:
        return {**result, "ok": False, "step": "garmin", "error": "Garmin rechazó la petición"}
    try:
        token = parse_token_response(body)
    except TokenError as exc:
        return {**result, "ok": False, "step": "parse", "error": str(exc)}
    return {**result, "ok": True, "token_expires_at": token.expires_at.isoformat()}
