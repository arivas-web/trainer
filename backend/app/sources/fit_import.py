"""Importación de archivos sueltos (FIT/GPX/TCX) o de un export completo de Garmin (zip,
con zips anidados). Siempre disponible como respaldo."""

import io
import logging
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.mapping.fit import ParsedActivity, parse_fit
from app.mapping.gpx_tcx import parse_gpx, parse_tcx
from app.mapping.persist import sha256, upsert_activity
from app.storage import FileStorage

log = logging.getLogger(__name__)

SUPPORTED = {".fit", ".gpx", ".tcx"}
MAX_ZIP_DEPTH = 3


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def merge(self, other: "ImportReport") -> None:
        self.created += other.created
        self.updated += other.updated
        self.skipped += other.skipped
        self.errors.extend(other.errors)


def iter_files(name: str, data: bytes, depth: int = 0) -> Iterator[tuple[str, bytes]]:
    """Recorre un archivo; si es zip, devuelve sus FIT/GPX/TCX (también en zips anidados)."""
    suffix = PurePosixPath(name.lower()).suffix
    if suffix == ".zip":
        if depth >= MAX_ZIP_DEPTH:
            return
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                inner = PurePosixPath(info.filename.lower()).suffix
                if inner in SUPPORTED or inner == ".zip":
                    yield from iter_files(info.filename, zf.read(info), depth + 1)
    elif suffix in SUPPORTED:
        yield name, data


def parse_any(name: str, data: bytes) -> ParsedActivity:
    suffix = PurePosixPath(name.lower()).suffix
    if suffix == ".fit":
        return parse_fit(data)
    if suffix == ".gpx":
        return parse_gpx(data)
    if suffix == ".tcx":
        return parse_tcx(data)
    raise ValueError(f"Formato no soportado: {suffix}")


def import_file(session: Session, storage: FileStorage, name: str, data: bytes) -> ImportReport:
    report = ImportReport()
    for fname, fdata in iter_files(name, data):
        try:
            parsed = parse_any(fname, fdata)
        except ValueError as exc:  # p. ej. FIT de monitorización en un export completo
            report.skipped += 1
            log.debug("Omitido %s: %s", fname, exc)
            continue
        except Exception as exc:
            report.errors.append(f"{fname}: {type(exc).__name__}: {exc}")
            continue
        suffix = PurePosixPath(fname.lower()).suffix
        key = f"imports/{sha256(fdata)}{suffix}"
        try:
            with session.begin_nested():
                storage.put(key, fdata)
                _, created = upsert_activity(
                    session,
                    parsed,
                    source=f"{suffix[1:]}_import",
                    file_bytes=fdata,
                    storage_key=key,
                )
        except Exception as exc:
            report.errors.append(f"{fname}: {type(exc).__name__}: {exc}")
            continue
        if created:
            report.created += 1
        else:
            report.updated += 1
    return report
