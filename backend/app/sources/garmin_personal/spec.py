"""Carga y validación de endpoints.toml."""

import tomllib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).with_name("endpoints.toml")

DAILY_KINDS = (
    "daily_summary",
    "sleep",
    "hrv",
    "stress",
    "body_composition",
    "spo2",
    "respiration",
    "user_metrics",
)


@dataclass(frozen=True)
class FieldSpec:
    path: str
    scale: float = 1.0


@dataclass(frozen=True)
class KindSpec:
    name: str
    path: str = ""
    start_param: str = ""
    end_param: str = ""
    date_format: str = "iso-date"
    max_days: int = 28
    items_path: str = ""
    key_field: str = ""
    date_field: str = ""
    page: dict[str, Any] | None = None
    fields: dict[str, FieldSpec] = field(default_factory=dict)
    extra_params: dict[str, Any] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        if self.name == "activity_file":
            return bool(self.path)
        return bool(self.path and self.start_param and self.end_param)

    def format_date(self, d: date, end: bool = False) -> str | int:
        if self.date_format == "iso-date":
            return d.isoformat()
        moment = datetime.combine(d, time.max if end else time.min, tzinfo=UTC)
        if self.date_format == "epoch-s":
            return int(moment.timestamp())
        if self.date_format == "epoch-ms":
            return int(moment.timestamp() * 1000)
        raise ValueError(f"date_format desconocido: {self.date_format}")


@dataclass(frozen=True)
class ApiSpec:
    data_auth_header: str
    data_auth_template: str
    kinds: dict[str, KindSpec]

    def kind(self, name: str) -> KindSpec:
        return self.kinds.get(name, KindSpec(name=name))


def _field(v: Any) -> FieldSpec:
    if isinstance(v, str):
        return FieldSpec(path=v)
    return FieldSpec(path=str(v["path"]), scale=float(v.get("scale", 1.0)))


def load_spec(path: Path = DEFAULT_PATH) -> ApiSpec:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    auth = raw.get("auth", {})
    kinds: dict[str, KindSpec] = {}
    for name, k in raw.get("kinds", {}).items():
        kinds[name] = KindSpec(
            name=name,
            path=k.get("path", ""),
            start_param=k.get("start_param", ""),
            end_param=k.get("end_param", ""),
            date_format=k.get("date_format", "iso-date"),
            max_days=int(k.get("max_days", 28)),
            items_path=k.get("items_path", ""),
            key_field=k.get("key_field", ""),
            date_field=k.get("date_field", ""),
            page=k.get("page"),
            fields={col: _field(v) for col, v in k.get("fields", {}).items()},
            extra_params=k.get("extra_params", {}),
        )
    return ApiSpec(
        data_auth_header=auth.get("data_auth_header", "Authorization"),
        data_auth_template=auth.get("data_auth_template", "Bearer {token}"),
        kinds=kinds,
    )


def dig(obj: Any, dotted: str) -> Any:
    """Sigue una ruta con puntos ("a.b.0.c") dentro de un JSON. Devuelve None si no existe."""
    if not dotted:
        return obj
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None:
            return None
    return cur
