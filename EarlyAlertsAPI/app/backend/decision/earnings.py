"""Earnings recommendation logic.

Pure function – no I/O.
"""
from __future__ import annotations

from app.backend.core.rule_pack import RulePack


def recommend_earnings(
    current_earnings_mxn: float,
    rule_pack: RulePack,
) -> tuple[float, float]:
    """Return (recommended_mxn, uplift_mxn).

    If current < target  → return (target, target - current).
    Otherwise           → return (current, 0.0).
    """
    target = rule_pack.earnings.target_mxn
    if current_earnings_mxn < target:
        uplift = round(target - current_earnings_mxn, 2)
        return target, uplift
    return current_earnings_mxn, 0.0
