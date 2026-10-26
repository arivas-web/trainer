"""Almacenamiento de archivos originales (FIT/GPX/TCX): disco local en desarrollo,
bucket privado de Supabase Storage en producción."""

from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class FileStorage(Protocol):
    def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None: ...
    def get(self, key: str) -> bytes | None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Clave de almacenamiento no válida")
        return p

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None


class SupabaseStorage:
    def __init__(self, url: str, service_key: str, bucket: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object/{bucket}"
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        resp = httpx.post(
            f"{self.base}/{key}",
            content=data,
            headers={**self.headers, "Content-Type": content_type, "x-upsert": "true"},
            timeout=60,
        )
        resp.raise_for_status()

    def get(self, key: str) -> bytes | None:
        resp = httpx.get(f"{self.base}/{key}", headers=self.headers, timeout=60)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content


def get_storage(settings: Settings | None = None) -> FileStorage:
    s = settings or get_settings()
    if s.storage_backend == "supabase":
        if not (s.supabase_url and s.supabase_service_role_key):
            raise RuntimeError(
                "STORAGE_BACKEND=supabase requiere SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY"
            )
        return SupabaseStorage(
            s.supabase_url, s.supabase_service_role_key.get_secret_value(), s.supabase_fit_bucket
        )
    return LocalStorage(s.local_data_dir / "files")
