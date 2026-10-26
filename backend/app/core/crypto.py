"""Cifrado simétrico (Fernet) para valores sensibles guardados en la base de datos."""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet | None:
    """TOKEN_ENCRYPTION_KEY si existe; si no, una clave derivada de la clave API de Garmin
    (quien lea la base de datos sin conocer la clave de Garmin no puede descifrar el token)."""
    s = get_settings()
    if s.token_encryption_key:
        return Fernet(s.token_encryption_key.get_secret_value().encode())
    if s.garmin_personal_api_key:
        digest = hashlib.sha256(
            b"pulse-token-cache-v1:" + s.garmin_personal_api_key.get_secret_value().encode()
        ).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    return None


def encrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("Sin clave para cifrar el token de Garmin")
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("Sin clave para descifrar el token de Garmin")
    return f.decrypt(value.encode()).decode()


def can_encrypt() -> bool:
    return _fernet() is not None
