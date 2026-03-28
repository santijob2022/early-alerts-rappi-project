"""Tests for orchestrator – full cycle + scenario 8 (provider failure)."""
from __future__ import annotations

import asyncio

import pytest


# ── Happy path: run_cycle succeeds ─────────────────────────────────────────
def test_happy_path_cycle_ok(
    in_memory_db, settings, rule_pack, zone_catalog, baseline_table, fake_provider
):
    """A dry cycle completes successfully, produces a run record."""
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session
    from app.backend.state import repo_runs

    with get_session() as conn:
        summary = asyncio.run(
            run_cycle(settings, rule_pack, zone_catalog, baseline_table, fake_provider, conn)
        )
        run_record = repo_runs.get_run(conn, summary.run_id)

    assert summary.status == "ok"
    assert summary.zones_evaluated == 14
    assert run_record is not None
    assert run_record["status"] == "ok"


# ── Scenario 8: provider failure – open events intact ──────────────────────
def test_s8_provider_failure_does_not_corrupt_events(
    in_memory_db, settings, rule_pack, zone_catalog, baseline_table, rainy_provider, failing_provider
):
    """After a provider failure, open events from a previous cycle remain open."""
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session
    from app.backend.state import repo_events

    # First cycle: open events with rain
    with get_session() as conn:
        summary1 = asyncio.run(
            run_cycle(settings, rule_pack, zone_catalog, baseline_table, rainy_provider, conn)
        )
    open_before = summary1.alerts_emitted

    # Second cycle: provider fails
    with get_session() as conn:
        summary2 = asyncio.run(
            run_cycle(settings, rule_pack, zone_catalog, baseline_table, failing_provider, conn)
        )
        open_after = repo_events.list_open_events(conn, settings.city)

    assert summary2.status == "failed"
    # Open events must not be touched
    assert len(open_after) >= (1 if open_before > 0 else 0)


# ── Decision records written per zone ────────────────────────────────────────
def test_decision_records_written_for_all_zones(
    in_memory_db, settings, rule_pack, zone_catalog, baseline_table, fake_provider
):
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session
    from app.backend.state import repo_decisions

    with get_session() as conn:
        summary = asyncio.run(
            run_cycle(settings, rule_pack, zone_catalog, baseline_table, fake_provider, conn)
        )
        decisions = repo_decisions.list_decisions_for_run(conn, summary.run_id)

    # One decision per zone at t+1
    assert len(decisions) >= 14


@pytest.fixture()
def rainy_provider():
    from app.backend.tests.conftest import FakeProvider
    return FakeProvider(precip_mm=3.0)
