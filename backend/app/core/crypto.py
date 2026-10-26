"""Cifrado simétrico (Fernet) para valores sensibles guardados en la base de datos."""

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet | None:
    key = get_settings().token_encryption_key
    return Fernet(key.get_secret_value().encode()) if key else None


def encrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("Falta TOKEN_ENCRYPTION_KEY para cifrar el token de Garmin")
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("Falta TOKEN_ENCRYPTION_KEY para descifrar el token de Garmin")
    return f.decrypt(value.encode()).decode()


def can_encrypt() -> bool:
    return _fernet() is not None
