"""Typer CLI for EarlyAlertsAPI.

Commands:
  run-once            Single forecast → decision → outbox cycle.
  serve               FastAPI + APScheduler long-running mode.
  list-open-events    Print currently open alert events from SQLite.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import typer
import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = typer.Typer(add_completion=False, help="Early Alerts API – Module 2c CLI")

_BASE = Path(__file__).parent


def _load_deps():
    """Load shared dependencies once (settings, rule_pack, zone_catalog, baseline)."""
    from app.backend.core.config import get_settings
    from app.backend.core.rule_pack import load_rule_pack
    from app.backend.core.zone_catalog import load_zone_catalog

    s = get_settings()
    rp = load_rule_pack(str(s.rule_pack_path))
    zc = load_zone_catalog(str(s.zone_catalog_path))
    with open(s.baseline_ratios_path, encoding="utf-8") as fh:
        bl = yaml.safe_load(fh)
    return s, rp, zc, bl


def _init_db(settings):
    from app.backend.state.database import init_db
    init_db(settings.storage.sqlite_path)


@app.command()
def run_once() -> None:
    """Fetch forecast, evaluate all zones, write to outbox (one cycle)."""
    from app.backend.ingestion.open_meteo import OpenMeteoProvider
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session
    from app.backend.state import repo_outbox

    s, rp, zc, bl = _load_deps()
    _init_db(s)

    provider = OpenMeteoProvider(
        base_url=s.provider.base_url,
        timeout_seconds=s.provider.timeout_seconds,
        max_retries=s.provider.max_retries,
    )

    with get_session() as conn:
        summary = asyncio.run(run_cycle(s, rp, zc, bl, provider, conn))

    typer.echo(f"\nRun {summary.run_id} | status: {summary.status}")
    typer.echo(f"Zones evaluated: {summary.zones_evaluated} | Alerts emitted: {summary.alerts_emitted}")

    with get_session() as conn:
        alerts = repo_outbox.get_pending_alerts(conn)

    if not alerts:
        typer.echo("\n── No alerts generated ──")
        typer.echo(f"Zones evaluated: {summary.zones_evaluated}")
        return

    typer.echo(f"\n{'─' * 54}")
    for alert in alerts:
        secondary = json.loads(alert.get("secondary_zones") or "[]")
        sec_str = ", ".join(secondary) if secondary else "–"
        typer.echo(
            f"{'ESCALATE' if alert['decision_type'] == 'escalate' else 'ALERT'} "
            f"| {alert['zone']} | Risk: {alert['risk_level'].upper()}"
        )
        typer.echo(f"  Precipitación esperada: {alert['precip_mm']:.1f} mm/hr en las próximas {alert['lead_time_min'] // 60}h")
        typer.echo(f"  Ratio proyectado: ~{alert['projected_ratio']:.2f} (basado en histórico)")
        typer.echo(
            f"  Acción: subir earnings de {s.earnings_baseline_mxn:.1f} "
            f"a {alert['recommended_earnings_mxn']:.1f} MXN "
            f"(+{alert['uplift_mxn']:.1f})"
        )
        typer.echo(f"  Zonas secundarias: {sec_str}")
        typer.echo(f"{'─' * 54}")


@app.command()
def serve() -> None:
    """Start FastAPI server + APScheduler background loop."""
    import uvicorn
    from app.backend.main import create_app

    _load_deps()  # validate config early
    uvicorn_app = create_app()
    uvicorn.run(uvicorn_app, host="0.0.0.0", port=8000, log_level="info")


@app.command()
def list_open_events() -> None:
    """Print all currently open alert events from SQLite."""
    from app.backend.state.database import get_session
    from app.backend.state import repo_events

    s, _, _, _ = _load_deps()
    _init_db(s)

    with get_session() as conn:
        events = repo_events.list_open_events(conn, s.city)

    if not events:
        typer.echo("No open events.")
        return

    typer.echo(f"\n{'─' * 70}")
    typer.echo(f"{'ID':36}  {'Zone':22}  {'Risk':6}  {'Opened':20}")
    typer.echo(f"{'─' * 70}")
    for ev in events:
        typer.echo(f"{ev['id']:36}  {ev['zone']:22}  {ev.get('max_risk') or '–':6}  {ev['opened_at'][:19]}")
    typer.echo(f"{'─' * 70}")
    typer.echo(f"Total open: {len(events)}")


if __name__ == "__main__":
    app()
