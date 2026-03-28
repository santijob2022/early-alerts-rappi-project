"""Single-cycle orchestration: fetch → ingest → decide → write state.

Memory logic (cooldown, escalation, dry-close) lives here, NOT in the engine.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
import asyncio
from datetime import datetime, timezone

from app.backend.core.config import Settings
from app.backend.core.constants import RISK_ORDER, DecisionType
from app.backend.core.models import DecisionInput, RunSummary, ZoneForecastRow
from app.backend.core.rule_pack import RulePack
from app.backend.core.zone_catalog import ZoneCatalog
from app.backend.decision.engine import evaluate_zone
from app.backend.ingestion.normalizer import normalize
from app.backend.ingestion.pipeline import run_pipeline
from app.backend.ingestion.provider_base import ForecastProvider
from app.backend.state import repo_config, repo_decisions, repo_events, repo_outbox, repo_runs

logger = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _should_suppress(open_event: dict, decision_output, rule_pack: RulePack, current_precip: float | None = None) -> bool:
    """Return True if this alert should be suppressed due to cooldown/no-escalation."""
    last_sent_str = open_event.get("last_sent_at")
    if not last_sent_str:
        return False

    last_sent = datetime.fromisoformat(last_sent_str.replace("Z", "+00:00"))
    if last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    elapsed_hours = (now - last_sent).total_seconds() / 3600

    if elapsed_hours >= rule_pack.memory.cooldown_hours:
        return False  # outside cooldown → allow resend

    # Inside cooldown: allow only if escalation criteria met
    if decision_output.risk_level is not None:
        current_risk_order = RISK_ORDER.get(decision_output.risk_level.value, 0)
        stored_risk_order = RISK_ORDER.get(open_event.get("max_risk", ""), 0)
        if current_risk_order > stored_risk_order:
            return False  # risk escalated → allow

    stored_precip = open_event.get("max_precip_mm") or 0.0
    # Use the explicit current_precip passed by the caller (forecast used by orchestrator).
    curr = current_precip
    # Use the precip threshold check via rule_pack: compare stored max_precip_mm against current forecast
    if stored_precip is not None and curr is not None:
        delta_precip = curr - stored_precip
        if delta_precip >= rule_pack.memory.resend_precip_delta_mm:
            return False

    return True  # suppress


async def run_cycle(
    settings: Settings,
    rule_pack: RulePack,
    zone_catalog: ZoneCatalog,
    baseline_table: dict,
    provider: ForecastProvider,
    conn,
) -> RunSummary:
    """Execute one full alert cycle. Returns RunSummary with counts."""
    run_id = _uuid()
    city = settings.city
    alerts_emitted = 0
    snapshot_id = run_id

    repo_runs.create_run(conn, run_id, city, rule_pack.version)
    # time the snapshot save for observability
    snap_start = time.monotonic()
    try:
        repo_config.save_snapshot(conn, _uuid(), run_id, settings.model_dump_json())
    except Exception as exc:  # keep behavior but log timing on error
        logger.exception("save_snapshot failed: %s", exc)
        raise
    finally:
        snap_dur = time.monotonic() - snap_start
        logger.info("save_snapshot duration=%.3fs", snap_dur)

    # --- Step 3: Fetch forecast ------------------------------------------
    centroids = [(z.latitude, z.longitude) for z in zone_catalog.zones]
    try:
        raw_responses = await provider.fetch_hourly_forecast(centroids, hours_ahead=6)
    except Exception as exc:
        logger.error("Provider fetch failed: %s", exc)
        repo_runs.finish_run(conn, run_id, "failed", 0, 0, error_message=str(exc))
        return RunSummary(
            run_id=run_id, status="failed", zones_evaluated=0, alerts_emitted=0, error=str(exc)
        )

    # --- Step 4: Ingest into DuckDB -------------------------------------
    fetched_at = datetime.now(timezone.utc)
    normalized_rows = normalize(raw_responses, centroids, zone_catalog, run_id, fetched_at)
    try:
        # Run dlt pipeline in background thread to avoid blocking the orchestrator.
        pl_start = time.monotonic()
        task = asyncio.create_task(
            asyncio.to_thread(
                run_pipeline,
                raw_responses,
                normalized_rows,
                run_id,
                settings.storage.duckdb_path,
            )
        )

        def _on_pipeline_done(t: asyncio.Task) -> None:
            try:
                res = t.result()
                dur = time.monotonic() - pl_start
                logger.info("dlt pipeline finished (background) snapshot_id=%s duration=%.3fs", res, dur)
            except Exception as exc:  # background failures are non-fatal for orchestrator
                dur = time.monotonic() - pl_start
                logger.warning("dlt pipeline background failed (non-fatal): %s (duration=%.3fs)", exc, dur)

        task.add_done_callback(_on_pipeline_done)
        # optimistic snapshot id; actual persistence happens asynchronously
        snapshot_id = run_id
    except Exception as exc:
        logger.warning("scheduling background dlt pipeline failed (non-fatal): %s", exc)

    # --- Step 5: Build zone_forecasts for t+1 ---------------------------
    now_local_hour = datetime.now(timezone.utc).astimezone().hour
    t1_hour = (now_local_hour + 1) % 24

    zone_t1: dict[str, ZoneForecastRow] = {}
    for row in normalized_rows:
        if row.forecast_hour == t1_hour:
            zone_t1[row.zone] = row

    zone_precip_t1: dict[str, float] = {z: r.precip_mm for z, r in zone_t1.items()}

    # --- Step 6: Evaluate each zone at t+1 ------------------------------
    zones_evaluated = 0
    for zone_info in zone_catalog.zones:
        zone = zone_info.name
        zones_evaluated += 1
        row = zone_t1.get(zone)
        precip = row.precip_mm if row else 0.0
        forecast_time_str = row.forecast_time.isoformat() if row else fetched_at.isoformat()

        inp = DecisionInput(
            zone=zone,
            forecast_hour=t1_hour,
            forecast_precip_mm=precip,
            current_hour=now_local_hour,
            current_earnings_mxn=settings.earnings_baseline_mxn,
        )
        open_event = repo_events.get_open_event(conn, city, zone)
        output = evaluate_zone(inp, rule_pack, baseline_table, open_event, zone_precip_t1, zone_catalog)

        # memory logic
        decision_id = _uuid()
        event_id = open_event["id"] if open_event else None

        if output.decision_type == DecisionType.SUPPRESS:
            if precip < rule_pack.memory.dry_threshold_mm and open_event:
                streak = repo_events.increment_dry_streak(conn, open_event["id"])
                if streak >= rule_pack.memory.dry_close_streak_hours:
                    repo_events.close_event(conn, open_event["id"])
                    logger.info("Closed event for %s (dry streak %d)", zone, streak)

        elif output.decision_type in (DecisionType.ALERT, DecisionType.ESCALATE):
            if open_event is None:
                event_id = _uuid()
                repo_events.open_event(
                    conn, event_id, city, zone,
                    max_risk=output.risk_level.value,
                    max_precip_mm=precip,
                )
                _enqueue(conn, event_id, output, city, zone, precip, forecast_time_str,
                         run_id, snapshot_id, rule_pack)
                alerts_emitted += 1
            else:
                suppress = _should_suppress(open_event, output, rule_pack, current_precip=precip)
                if not suppress:
                    new_risk = output.risk_level.value if output.risk_level else open_event["max_risk"]
                    new_precip = max(precip, open_event.get("max_precip_mm") or 0.0)
                    actual_type = DecisionType.ESCALATE if (
                        output.risk_level and
                        RISK_ORDER.get(output.risk_level.value, 0) > RISK_ORDER.get(open_event.get("max_risk", ""), 0)
                    ) else DecisionType.ALERT
                    output = output.model_copy(update={"decision_type": actual_type})
                    repo_events.update_event(conn, open_event["id"], max_risk=new_risk, max_precip_mm=new_precip)
                    repo_events.reset_dry_streak(conn, open_event["id"])
                    _enqueue(conn, open_event["id"], output, city, zone, precip, forecast_time_str,
                             run_id, snapshot_id, rule_pack)
                    alerts_emitted += 1
                    event_id = open_event["id"]
                else:
                    output = output.model_copy(update={"decision_type": DecisionType.SUPPRESS})

        elif output.decision_type == DecisionType.WATCH and open_event:
            repo_events.reset_dry_streak(conn, open_event["id"])

        repo_decisions.record_decision(
            conn,
            decision_id=decision_id,
            run_id=run_id,
            zone=zone,
            forecast_hour=t1_hour,
            forecast_time=forecast_time_str,
            precip_mm=precip,
            decision_type=output.decision_type.value,
            event_id=event_id,
            risk_level=output.risk_level.value if output.risk_level else None,
            projected_ratio=output.projected_ratio,
            recommended_earnings_mxn=output.recommended_earnings_mxn,
            uplift_mxn=output.uplift_mxn,
            lead_time_min=output.lead_time_min,
            secondary_zones=output.secondary_zones,
            reason=output.reason,
        )

    # --- Step 7: Watchlist (t+2, t+3) -----------------------------------
    for horizon_offset in (2, 3):
        t_hour = (now_local_hour + horizon_offset) % 24
        for row in normalized_rows:
            if row.forecast_hour != t_hour:
                continue
            zone = row.zone
            is_sensitive = zone in rule_pack.sensitive_zones
            is_peak = t_hour in rule_pack.peak_hours
            trigger = rule_pack.triggers.sensitive_peak_mm if (is_sensitive and is_peak) else rule_pack.triggers.base_mm
            if row.precip_mm >= trigger:
                repo_decisions.record_decision(
                    conn,
                    decision_id=_uuid(),
                    run_id=run_id,
                    zone=zone,
                    forecast_hour=t_hour,
                    forecast_time=row.forecast_time.isoformat(),
                    precip_mm=row.precip_mm,
                    decision_type="watch",
                    lead_time_min=horizon_offset * 60,
                    reason=f"Watchlist t+{horizon_offset}: {row.precip_mm:.1f} mm/hr",
                )

    # --- Step 8: Finish run ---------------------------------------------
    repo_runs.finish_run(conn, run_id, "ok", zones_evaluated, alerts_emitted, snapshot_id=snapshot_id)

    return RunSummary(
        run_id=run_id,
        status="ok",
        zones_evaluated=zones_evaluated,
        alerts_emitted=alerts_emitted,
    )


def _enqueue(
    conn,
    event_id: str,
    output,
    city: str,
    zone: str,
    precip_mm: float,
    forecast_time_str: str,
    run_id: str,
    snapshot_id: str,
    rule_pack: RulePack,
) -> None:
    repo_outbox.enqueue_alert(
        conn,
        outbox_id=_uuid(),
        event_id=event_id,
        city=city,
        zone=zone,
        forecast_time=forecast_time_str,
        precip_mm=precip_mm,
        risk_level=output.risk_level.value if output.risk_level else "medio",
        projected_ratio=output.projected_ratio or 0.0,
        recommended_earnings_mxn=output.recommended_earnings_mxn,
        uplift_mxn=output.uplift_mxn,
        lead_time_min=output.lead_time_min,
        secondary_zones=output.secondary_zones,
        reason=output.reason,
        decision_type=output.decision_type.value,
        run_id=run_id,
        source_snapshot_id=snapshot_id,
        rule_pack_version=rule_pack.version,
    )
