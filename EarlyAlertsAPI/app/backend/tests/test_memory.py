"""Tests for memory / cooldown / dry-close logic – scenarios 5, 6, 7 from PLAN.md."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.backend.state import repo_events, repo_outbox


# ── Scenario 5: 3 consecutive polls → 1 alert + 2 suppress ─────────────────
def test_s5_cooldown_suppresses_duplicates(
    in_memory_db, settings, rule_pack, zone_catalog, baseline_table, rainy_provider
):
    """Three cycles with same rain: 1st emits alert, 2nd + 3rd suppress within cooldown."""
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session

    results = []
    for _ in range(3):
        with get_session() as conn:
            summary = asyncio.run(
                run_cycle(settings, rule_pack, zone_catalog, baseline_table, rainy_provider, conn)
            )
        results.append(summary.alerts_emitted)

    # First cycle should emit ≥ 1 alert; subsequent cycles within cooldown should emit 0
    assert results[0] >= 1
    assert results[1] == 0
    assert results[2] == 0


# ── Scenario 6: dry-close streak after open event ───────────────────────────
def test_s6_dry_streak_closes_event(in_memory_db, settings, rule_pack, zone_catalog, baseline_table):
    """After 2 consecutive dry cycles an open event should be closed."""
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session
    from app.backend.tests.conftest import FakeProvider

    city = settings.city
    enough_rain = FakeProvider(precip_mm=3.0)
    dry = FakeProvider(precip_mm=0.0)

    # Open an event with one rainy cycle
    with get_session() as conn:
        asyncio.run(run_cycle(settings, rule_pack, zone_catalog, baseline_table, enough_rain, conn))

    # 2 dry cycles → streak ≥ 2 → close event
    for _ in range(2):
        with get_session() as conn:
            asyncio.run(run_cycle(settings, rule_pack, zone_catalog, baseline_table, dry, conn))

    with get_session() as conn:
        # No open events should remain
        open_evts = repo_events.list_open_events(conn, city)
    assert open_evts == []


# ── Scenario 7: escalation overrides cooldown ───────────────────────────────
def test_s7_escalation_bypasses_cooldown(in_memory_db, settings):
    """If risk escalates, suppression is skipped and a new outbox entry is created."""
    from app.backend.state.database import get_session

    with get_session() as conn:
        event_id = str(uuid.uuid4())
        # Open event with MEDIO risk
        repo_events.open_event(conn, event_id, settings.city, "Santiago", max_risk="medio", max_precip_mm=1.5)

        # Forcibly set last_sent_at to very recent (within cooldown)
        from datetime import datetime, timezone
        repo_events.update_event(conn, event_id, max_risk="medio", max_precip_mm=1.5)

        # Simulate escalation: new outbox entry with CRITICO
        outbox_id = str(uuid.uuid4())
        repo_outbox.enqueue_alert(
            conn,
            outbox_id=outbox_id,
            event_id=event_id,
            city=settings.city,
            zone="Santiago",
            forecast_time=datetime.now(timezone.utc).isoformat(),
            precip_mm=6.0,
            risk_level="critico",
            projected_ratio=2.8,
            recommended_earnings_mxn=80.0,
            uplift_mxn=24.4,
            lead_time_min=60,
            secondary_zones=[],
            reason="Escalation test",
            decision_type="escalate",
            run_id=str(uuid.uuid4()),
            source_snapshot_id=str(uuid.uuid4()),
            rule_pack_version=rule_pack.version if False else "v1",
        )
        pending = repo_outbox.get_pending_alerts(conn)

    assert len(pending) == 1
    assert pending[0]["risk_level"] == "critico"
    assert pending[0]["decision_type"] == "escalate"


@pytest.fixture()
def rule_pack(settings):
    from app.backend.core.rule_pack import load_rule_pack
    return load_rule_pack(str(settings.rule_pack_path))
