"""Interfaz común de las fuentes de datos. El resto de la app solo conoce `GarminSource`."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass
class CallRecord:
    """Traza de una llamada HTTP para el log de sincronización (sin secretos)."""

    data_type: str
    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    http_code: int | None = None
    items: int | None = None
    error: str | None = None
    duration_ms: float | None = None


CallListener = Callable[[CallRecord], None]


class SourceNotConfiguredError(RuntimeError):
    """El tipo de dato no está mapeado todavía (falta en endpoints.toml)."""


class GarminSource(Protocol):
    name: str

    def range_kinds(self) -> list[str]:
        """Tipos de dato que se piden por rango de fechas y están configurados."""
        ...

    def max_range_days(self, kind: str) -> int: ...

    def fetch_range(self, kind: str, start: date, end: date) -> list[dict[str, Any]]:
        """Registros crudos de `kind` entre `start` y `end` (ambos incluidos)."""
        ...

    def record_key(self, kind: str, record: dict[str, Any]) -> str:
        """Clave estable del registro (id de actividad, fecha de calendario...)."""
        ...

    def activity_file(self, activity_ref: str) -> bytes | None:
        """FIT original de una actividad, si la fuente lo ofrece."""
        ...
