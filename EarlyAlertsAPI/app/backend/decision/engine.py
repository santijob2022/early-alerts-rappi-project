"""Decision engine: pure function mapping forecast context → DecisionOutput.

All business logic comes from Motor_Reglas_y_Alertas.md pseudocode.
No I/O, no side effects.
"""
from __future__ import annotations

from app.backend.core.constants import DecisionType, RiskLevel
from app.backend.core.models import AlertEvent, DecisionInput, DecisionOutput
from app.backend.core.rule_pack import RulePack
from app.backend.core.zone_catalog import ZoneCatalog
from app.backend.decision.earnings import recommend_earnings
from app.backend.decision.projections import project_ratio
from app.backend.decision.secondary_zones import rank_secondary_zones
from app.backend.decision.severity import classify_risk


def _compute_lead_time(forecast_hour: int, current_hour: int) -> int:
    """Lead time in minutes; minimum 60 (never report 0)."""
    delta = (forecast_hour - current_hour) % 24
    return max(delta * 60, 60)


def _build_suppress(reason: str) -> DecisionOutput:
    return DecisionOutput(
        decision_type=DecisionType.SUPPRESS,
        risk_level=None,
        projected_ratio=None,
        recommended_earnings_mxn=0.0,
        uplift_mxn=0.0,
        lead_time_min=0,
        secondary_zones=[],
        reason=reason,
    )


def _build_watch(reason: str, lead_time_min: int) -> DecisionOutput:
    return DecisionOutput(
        decision_type=DecisionType.WATCH,
        risk_level=None,
        projected_ratio=None,
        recommended_earnings_mxn=0.0,
        uplift_mxn=0.0,
        lead_time_min=lead_time_min,
        secondary_zones=[],
        reason=reason,
    )


def evaluate_zone(
    input: DecisionInput,
    rule_pack: RulePack,
    baseline_table: dict,
    open_event: AlertEvent | None,
    zone_forecasts: dict[str, float],
    zone_catalog: ZoneCatalog,
) -> DecisionOutput:
    """Evaluate a single zone at a single forecast horizon.

    Returns a DecisionOutput; memory/outbox logic lives in the orchestrator.
    Radon CC ≤ 10 (sub-functions handle branching).
    """
    zone = input.zone
    precip_mm = input.forecast_precip_mm
    forecast_hour = input.forecast_hour
    current_hour = input.current_hour

    is_peak = forecast_hour in rule_pack.peak_hours
    is_sensitive = zone in rule_pack.sensitive_zones
    trigger_mm = (
        rule_pack.triggers.sensitive_peak_mm
        if (is_peak and is_sensitive)
        else rule_pack.triggers.base_mm
    )

    lead_time_min = _compute_lead_time(forecast_hour, current_hour)

    # --- 1. Watchlist-only horizon (t+2 / t+3, lead > 60 min) -----------
    if lead_time_min > 60:
        if precip_mm >= trigger_mm:
            return _build_watch(
                f"Watchlist horizon ({lead_time_min} min); precip {precip_mm:.1f} mm/hr",
                lead_time_min,
            )
        return _build_suppress(f"Lead {lead_time_min} min, precip below trigger")

    # --- 2. Dry at t+1 ---------------------------------------------------
    if precip_mm < rule_pack.memory.dry_threshold_mm:
        return _build_suppress("Dry conditions at t+1")

    # --- 3. Project ratio ------------------------------------------------
    projected = project_ratio(zone, forecast_hour, precip_mm, rule_pack, baseline_table)
    risk = classify_risk(projected, precip_mm, rule_pack)

    # --- 4. Below trigger → WATCH ----------------------------------------
    if precip_mm < trigger_mm:
        return _build_watch(
            f"Precip {precip_mm:.1f} < trigger {trigger_mm:.1f} mm/hr", lead_time_min
        )

    # --- 5. MEDIO non-sensitive non-peak → WATCH -------------------------
    if risk == RiskLevel.MEDIO and not (is_peak and is_sensitive):
        return _build_watch(
            f"Risk MEDIO – not actionable outside sensitive+peak", lead_time_min
        )

    # --- 6. No actionable risk level → SUPPRESS --------------------------
    if risk is None:
        return _build_suppress(
            f"Projected ratio {projected:.2f} below notifiable floor"
        )

    # --- 7. Compute earnings & secondary zones ---------------------------
    rec_earnings, uplift = recommend_earnings(input.current_earnings_mxn, rule_pack)
    secondary = rank_secondary_zones(zone, zone_forecasts, rule_pack, zone_catalog)

    decision_type = DecisionType.ALERT

    return DecisionOutput(
        decision_type=decision_type,
        risk_level=risk,
        projected_ratio=projected,
        recommended_earnings_mxn=rec_earnings,
        uplift_mxn=uplift,
        lead_time_min=lead_time_min,
        secondary_zones=secondary,
        reason=(
            f"Precipitación {precip_mm:.1f} mm/hr ≥ trigger {trigger_mm:.1f}; "
            f"ratio proyectado {projected:.2f}; riesgo {risk.value}"
        ),
    )
