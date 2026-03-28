"""Enums shared across the entire backend. No business logic here."""
from enum import Enum


class RiskLevel(str, Enum):
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"


class DecisionType(str, Enum):
    WATCH = "watch"
    ALERT = "alert"
    ESCALATE = "escalate"
    SUPPRESS = "suppress"


class OutboxStatus(str, Enum):
    PENDING = "pending"
    CONSUMED = "consumed"
    SUPPRESSED = "suppressed"


class RainBucket(str, Enum):
    DRY = "dry"
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"


class EventStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


# Ordering for risk-level comparison (higher index = more severe)
RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.MEDIO: 0,
    RiskLevel.ALTO: 1,
    RiskLevel.CRITICO: 2,
}
