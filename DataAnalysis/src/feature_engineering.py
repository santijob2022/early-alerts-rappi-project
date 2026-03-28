"""
feature_engineering.py — KPI computation, ratio labels, and rain segmentation.
"""
import numpy as np
import pandas as pd

from src.config import (
    RATIO_OVER_SUPPLY,
    RATIO_LOW,
    RATIO_HEALTHY_HIGH,
    RATIO_HIGH,
    RATIO_SATURATION,
    RAIN_BUCKET_BINS,
    RAIN_BUCKET_LABELS,
)


# ---------------------------------------------------------------------------
# Core KPIs (safe division throughout)
# ---------------------------------------------------------------------------

def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Return numerator / denominator; yields NaN where denominator == 0."""
    return numerator / denominator.replace(0, np.nan)


def compute_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add RATIO = ORDERS / CONNECTED_RT.
    Interpretation: rider utilisation / saturation index.
    """
    df = df.copy()
    df["RATIO"] = _safe_divide(df["ORDERS"], df["CONNECTED_RT"])
    return df


def compute_earnings_per_order(df: pd.DataFrame) -> pd.DataFrame:
    """Add EARNINGS_PER_ORDER = EARNINGS / ORDERS."""
    df = df.copy()
    df["EARNINGS_PER_ORDER"] = _safe_divide(df["EARNINGS"], df["ORDERS"])
    return df


def compute_earnings_per_rider(df: pd.DataFrame) -> pd.DataFrame:
    """Add EARNINGS_PER_RIDER = EARNINGS / CONNECTED_RT."""
    df = df.copy()
    df["EARNINGS_PER_RIDER"] = _safe_divide(df["EARNINGS"], df["CONNECTED_RT"])
    return df


def compute_supply_demand_gap(df: pd.DataFrame) -> pd.DataFrame:
    """Add SUPPLY_DEMAND_GAP = CONNECTED_RT - ORDERS (positive = over-supply)."""
    df = df.copy()
    df["SUPPLY_DEMAND_GAP"] = df["CONNECTED_RT"] - df["ORDERS"]
    return df


def add_all_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all KPI transforms in one call."""
    df = compute_ratio(df)
    df = compute_earnings_per_order(df)
    df = compute_earnings_per_rider(df)
    df = compute_supply_demand_gap(df)
    return df


# ---------------------------------------------------------------------------
# Bucket labels
# ---------------------------------------------------------------------------

def label_saturation_bucket(ratio_series: pd.Series) -> pd.Series:
    """
    Map RATIO values to categorical saturation labels.

    Buckets (from Rappi case document)
    ------------------------------------
    < 0.5  → "over_supply"
    0.5–0.9 → "low_utilization"
    0.9–1.2 → "healthy"
    1.2–1.8 → "high_utilization"
    > 1.8  → "saturation"
    NaN    → "unknown"
    """
    bins   = [float("-inf"), RATIO_OVER_SUPPLY, RATIO_LOW,
              RATIO_HEALTHY_HIGH, RATIO_HIGH, float("inf")]
    labels = ["over_supply", "low_utilization", "healthy",
              "high_utilization", "saturation"]

    bucketed = pd.cut(ratio_series, bins=bins, labels=labels, right=False)
    return bucketed.astype(str).replace("nan", "unknown")


def label_rain_bucket(precip_series: pd.Series) -> pd.Series:
    """
    Map PRECIPITATION_MM to categorical rain labels.

    Buckets
    -------
    0.0         → "no_rain"
    0.0–2.0 mm/hr → "light"
    2.0–5.0 mm/hr → "moderate"
    > 5.0 mm/hr → "heavy"
    """
    bucketed = pd.cut(
        precip_series,
        bins=RAIN_BUCKET_BINS,
        labels=RAIN_BUCKET_LABELS,
        right=False,
        include_lowest=True,
    )
    return bucketed.astype(str).replace("nan", "unknown")


def add_all_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Add SATURATION_BUCKET and RAIN_BUCKET columns."""
    df = df.copy()
    if "RATIO" not in df.columns:
        df = compute_ratio(df)
    df["SATURATION_BUCKET"] = label_saturation_bucket(df["RATIO"])
    if "PRECIPITATION_MM" in df.columns:
        df["RAIN_BUCKET"] = label_rain_bucket(df["PRECIPITATION_MM"])
    return df
