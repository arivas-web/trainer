"""CLI de Pulse: `uv run python -m app.cli --help`."""

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import typer

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db import get_sessionmaker, session_scope

cli = typer.Typer(help="Pulse · laboratorio personal de rendimiento", no_args_is_help=True)


@cli.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    setup_logging(logging.DEBUG if verbose else logging.INFO)


@cli.command()
def migrate() -> None:
    """Aplica las migraciones de Alembic (DATABASE_URL)."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    typer.echo("Migraciones aplicadas.")


@cli.command("token-check")
def token_check() -> None:
    """Comprueba la clave API personal y muestra la FORMA de la respuesta (sin valores)."""
    from app.sources.garmin_personal.probe import shape

    s = get_settings()
    if s.garmin_personal_api_key is None:
        typer.echo("Falta GARMIN_PERSONAL_API_KEY en .env.local", err=True)
        raise typer.Exit(1)
    resp = httpx.post(
        s.garmin_token_url,
        headers={"Authorization": f"ApiKey {s.garmin_personal_api_key.get_secret_value()}"},
        timeout=30,
    )
    typer.echo(f"HTTP {resp.status_code} · content-type: {resp.headers.get('content-type')}")
    try:
        typer.echo(json.dumps(shape(resp.json()), indent=2, ensure_ascii=False))
    except ValueError:
        typer.echo(f"(cuerpo no JSON, {len(resp.content)} bytes)")


@cli.command()
def probe(
    spec: Path = typer.Option(None, help="Ruta al OpenAPI (por defecto GARMIN_OPENAPI_PATH)"),
    days: int = typer.Option(7, help="Días hacia atrás para los parámetros de fecha"),
    call: bool = typer.Option(False, "--call", help="Llamar a la API (si no, solo lista)"),
    save_raw: bool = typer.Option(
        False, "--save-raw", help="Guardar respuestas completas en data/probe (NO compartir)"
    ),
) -> None:
    """Lista los endpoints GET del OpenAPI y, con --call, la forma de cada respuesta."""
    from app.sources.garmin_personal import probe as p
    from app.sources.garmin_personal.spec import load_spec
    from app.sync.factory import build_token_provider

    s = get_settings()
    spec_path = spec or s.garmin_openapi_path
    if not spec_path.exists():
        typer.echo(f"No encuentro el OpenAPI en {spec_path}", err=True)
        raise typer.Exit(1)
    doc = p.load_openapi(spec_path)
    ops = p.list_operations(doc)
    typer.echo(f"{len(ops)} operaciones GET en {spec_path.name} (servidor: {p.base_url(doc)})")
    for op in ops:
        q = ", ".join(
            f"{x['name']}{'*' if x.get('required') else ''}:{x.get('schema', {}).get('type', '?')}"
            for x in op.query_params
        )
        typer.echo(f"  GET {op.path}  [{q}]  {op.summary}")
    if not call:
        return
    http = httpx.Client(timeout=30)
    api = load_spec()
    results = p.probe(
        doc,
        build_token_provider(s, get_sessionmaker(), http),
        http,
        base=p.base_url(doc) or s.garmin_api_base,
        days=days,
        auth_header=api.data_auth_header,
        auth_template=api.data_auth_template,
        save_dir=(s.local_data_dir / "probe") if save_raw else None,
    )
    out = [
        {
            "path": r.operation.path,
            "params": r.params,
            "status": r.status,
            "content_type": r.content_type,
            "shape": r.shape,
            "error": r.error,
        }
        for r in results
    ]
    target = s.local_data_dir / "probe_shapes.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    for r in results:
        typer.echo(f"  {r.status or '—'}  {r.operation.path}  {r.error or ''}")
    typer.echo(f"\nFormas guardadas en {target} (sin valores: se pueden compartir).")


@cli.command()
def sync(
    full: bool = typer.Option(False, help="Ignorar el estado y re-sincronizar el histórico"),
    days: int = typer.Option(None, help="Días de histórico (por defecto SYNC_INITIAL_DAYS)"),
) -> None:
    """Sincroniza con Garmin hasta terminar, mostrando el progreso, y luego el resumen."""
    from app.sync.factory import build_worker
    from app.sync.service import plan_run, run_status

    s = get_settings()
    worker, source = build_worker(s)
    if not source.range_kinds():
        typer.echo(
            "Ningún tipo de dato de Garmin está configurado todavía (endpoints.toml).\n"
            "Hace falta el OpenAPI oficial de la Personal API para mapearlos."
        )
    with session_scope() as ses:
        run_id = plan_run(
            ses,
            source,
            date.today(),
            initial_days=days or s.sync_initial_days,
            resync_days=s.sync_resync_daily_days,
            full=full,
        )
    started = time.monotonic()
    while True:
        res = worker.tick(budget_s=10)
        with session_scope() as ses:
            st = run_status(ses, run_id)
        bar = "█" * int(st["progress"] * 30)
        sys.stdout.write(
            f"\r[{bar:<30}] {st['progress'] * 100:5.1f}%  "
            f"{st['finished_jobs']}/{st['total_jobs']} trabajos  "
            f"{time.monotonic() - started:5.0f}s"
        )
        sys.stdout.flush()
        if res.remaining == 0 or (res.processed == 0):
            break
    typer.echo("")
    for e in st["errors"]:
        typer.echo(f"  ⚠ {e}")
    summary(as_json=False)


@cli.command()
def summary(as_json: bool = typer.Option(False, "--json")) -> None:
    """Resumen de lo descargado: actividades por deporte, fechas y métricas que llegan."""
    from app.sync.summary import build_summary, format_summary

    with session_scope() as ses:
        data = build_summary(ses)
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False) if as_json else format_summary(data))


@cli.command("import")
def import_cmd(paths: list[Path]) -> None:
    """Importa FIT/GPX/TCX sueltos, carpetas o el export completo de Garmin (.zip)."""
    from app.sources.fit_import import ImportReport, import_file
    from app.storage import get_storage

    storage = get_storage()
    total = ImportReport()
    files = [f for p in paths for f in (sorted(p.rglob("*")) if p.is_dir() else [p]) if f.is_file()]
    for i, f in enumerate(files, 1):
        with session_scope() as ses:
            rep = import_file(ses, storage, f.name, f.read_bytes())
        total.merge(rep)
        typer.echo(
            f"[{i}/{len(files)}] {f.name}: +{rep.created} nuevas, {rep.updated} actualizadas, "
            f"{rep.skipped} omitidas, {len(rep.errors)} errores"
        )
    typer.echo(
        f"\nTotal: {total.created} nuevas · {total.updated} actualizadas · "
        f"{total.skipped} omitidas · {len(total.errors)} errores"
    )
    for e in total.errors[:20]:
        typer.echo(f"  ⚠ {e}")


if __name__ == "__main__":
    cli()
