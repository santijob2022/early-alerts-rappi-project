"""Risk classification from projected ratio and precipitation.

Pure function – no I/O.
"""
from __future__ import annotations

from app.backend.core.constants import RiskLevel
from app.backend.core.rule_pack import RulePack


def classify_risk(
    projected_ratio: float,
    precip_mm: float,
    rule_pack: RulePack,
) -> RiskLevel | None:
    """Map projected ratio → RiskLevel, None if below notifiable floor.

    Overrides (from Motor_Reglas_y_Alertas.md):
      - precip_mm >= 5.0 AND already notifiable ( ≥ ALTO) → force CRITICO.
    """
    t = rule_pack.severity_thresholds
    if projected_ratio < t.medio_min:
        return None
    if projected_ratio < t.alto_min:
        level = RiskLevel.MEDIO
    elif projected_ratio < t.critico_min:
        level = RiskLevel.ALTO
    else:
        level = RiskLevel.CRITICO

    # Heavy-rain override
    if precip_mm >= rule_pack.triggers.critical_escalation_mm and level in (
        RiskLevel.ALTO,
        RiskLevel.CRITICO,
    ):
        return RiskLevel.CRITICO

    return level
