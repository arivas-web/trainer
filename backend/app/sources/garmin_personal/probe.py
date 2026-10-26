"""Exploración de la Personal API a partir de su especificación OpenAPI oficial.

1. `list_operations` lee el OpenAPI y devuelve las operaciones GET con sus parámetros.
2. `probe` llama a cada una con un rango de fechas reciente y devuelve la FORMA de la
   respuesta (campos, tipos, longitud de listas), nunca los valores. Esa salida es segura
   para compartir y es la base para rellenar endpoints.toml sin inventar nada.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.sources.garmin_personal.auth import TokenProvider

DATE_HINTS = re.compile(r"(start|end|from|to|date|day|time)", re.IGNORECASE)


@dataclass
class Operation:
    path: str
    operation_id: str
    summary: str
    params: list[dict[str, Any]] = field(default_factory=list)

    @property
    def path_params(self) -> list[str]:
        return [p["name"] for p in self.params if p.get("in") == "path"]

    @property
    def query_params(self) -> list[dict[str, Any]]:
        return [p for p in self.params if p.get("in") == "query"]


def load_openapi(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Para leer YAML instala pyyaml o convierte el spec a JSON") from exc
        data: dict[str, Any] = yaml.safe_load(text)
        return data
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def _resolve(spec: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    ref = obj.get("$ref")
    if not ref:
        return obj
    node: Any = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return dict(node)


def list_operations(spec: dict[str, Any]) -> list[Operation]:
    ops: list[Operation] = []
    for path, item in spec.get("paths", {}).items():
        shared = [_resolve(spec, p) for p in item.get("parameters", [])]
        get = item.get("get")
        if not get:
            continue
        params = shared + [_resolve(spec, p) for p in get.get("parameters", [])]
        ops.append(
            Operation(
                path=path,
                operation_id=get.get("operationId", path),
                summary=get.get("summary", ""),
                params=params,
            )
        )
    return ops


def base_url(spec: dict[str, Any]) -> str | None:
    servers = spec.get("servers") or []
    return str(servers[0]["url"]).rstrip("/") if servers else None


def shape(value: Any, depth: int = 0, max_depth: int = 6) -> Any:
    """Estructura sin valores: {"campo": "int"}, listas como [forma_del_primero, "×n"]."""
    if depth > max_depth:
        return "…"
    if isinstance(value, dict):
        return {k: shape(v, depth + 1, max_depth) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return ["(vacía)"]
        return [shape(value[0], depth + 1, max_depth), f"×{len(value)}"]
    if value is None:
        return "null"
    return type(value).__name__


def guess_params(op: Operation, start: date, end: date) -> dict[str, Any]:
    """Rellena parámetros obligatorios de fecha usando el tipo/format del OpenAPI."""
    out: dict[str, Any] = {}
    for p in op.query_params:
        name = p["name"]
        schema = p.get("schema", {})
        if not DATE_HINTS.search(name):
            if p.get("required") and "default" in schema:
                out[name] = schema["default"]
            continue
        is_end = bool(re.search(r"(end|to)", name, re.IGNORECASE))
        d = end if is_end else start
        fmt, typ = schema.get("format", ""), schema.get("type", "string")
        if typ == "integer":
            secs = int((d - date(1970, 1, 1)).total_seconds()) + (86399 if is_end else 0)
            out[name] = secs * 1000 if "ms" in name.lower() or fmt == "int64" else secs
        elif fmt == "date-time":
            out[name] = f"{d.isoformat()}T{'23:59:59' if is_end else '00:00:00'}Z"
        else:
            out[name] = d.isoformat()
    return out


@dataclass
class ProbeResult:
    operation: Operation
    url: str
    params: dict[str, Any]
    status: int | None
    content_type: str | None
    shape: Any
    error: str | None = None


def probe(
    spec: dict[str, Any],
    tokens: TokenProvider,
    http: httpx.Client,
    *,
    base: str,
    days: int = 7,
    auth_header: str = "Authorization",
    auth_template: str = "Bearer {token}",
    save_dir: Path | None = None,
) -> list[ProbeResult]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    results: list[ProbeResult] = []
    for op in list_operations(spec):
        if op.path_params:
            results.append(
                ProbeResult(op, op.path, {}, None, None, None, "requiere parámetros de ruta")
            )
            continue
        params = guess_params(op, start, end)
        url = f"{base}{op.path}"
        try:
            resp = http.get(
                url,
                params=params,
                headers={auth_header: auth_template.format(token=tokens.get())},
            )
        except httpx.HTTPError as exc:
            results.append(ProbeResult(op, url, params, None, None, None, str(exc)))
            continue
        ctype = resp.headers.get("content-type", "")
        body_shape: Any = None
        if "json" in ctype and resp.content:
            body = resp.json()
            body_shape = shape(body)
            if save_dir is not None:
                save_dir.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", op.operation_id)
                (save_dir / f"{safe}.json").write_text(json.dumps(body, indent=2))
        elif resp.content:
            body_shape = f"<{ctype or 'binario'}: {len(resp.content)} bytes>"
        err = None if resp.status_code < 400 else resp.text[:200]
        results.append(ProbeResult(op, url, params, resp.status_code, ctype, body_shape, err))
    return results
