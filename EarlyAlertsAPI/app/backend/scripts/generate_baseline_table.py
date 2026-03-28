"""One-time script: compute dry-condition baseline ratios from historical parquet.

Usage (from EarlyAlertsAPI/ root):
    uv run app/backend/scripts/generate_baseline_table.py

Output: app/backend/data/baseline_ratios.yaml
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd
import yaml


PARQUET_PATH = (
    Path(__file__).resolve().parents[4]
    / "DataAnalysis"
    / "outputs"
    / "cleaned"
    / "raw_data_clean.parquet"
)
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "baseline_ratios.yaml"

PEAK_HOURS = {12, 13, 14, 19, 20, 21}
DRY_THRESHOLD_MM = 0.1


def _strip_accents(text: str) -> str:
    """Remove diacritics so zone names match catalog (e.g. Huinalá → Huinala)."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def main() -> None:
    print(f"Reading parquet: {PARQUET_PATH}")
    df = pd.read_parquet(PARQUET_PATH)

    # Drop explicitly invalid rows
    df = df[~df["IS_INVALID"]].copy()

    # Compute ratio; drop rows where CONNECTED_RT == 0
    df = df[df["CONNECTED_RT"] > 0].copy()
    df["RATIO"] = df["ORDERS"] / df["CONNECTED_RT"]

    # Keep only dry conditions
    df = df[df["PRECIPITATION_MM"] < DRY_THRESHOLD_MM].copy()

    # Normalize zone names (strip diacritics)
    df["ZONE_KEY"] = df["ZONE"].apply(_strip_accents)

    print(f"Dry rows after filtering: {len(df):,}")

    # --- by_zone_hour ---
    zh = (
        df.groupby(["ZONE_KEY", "HOUR"])["RATIO"]
        .mean()
        .reset_index()
    )
    by_zone_hour: dict = {}
    for _, row in zh.iterrows():
        zone = row["ZONE_KEY"]
        hour = int(row["HOUR"])
        ratio = round(float(row["RATIO"]), 4)
        by_zone_hour.setdefault(zone, {})[hour] = ratio

    # --- by_zone_period ---
    df["IS_PEAK"] = df["HOUR"].isin(PEAK_HOURS)
    zp = (
        df.groupby(["ZONE_KEY", "IS_PEAK"])["RATIO"]
        .mean()
        .reset_index()
    )
    by_zone_period: dict = {}
    for _, row in zp.iterrows():
        zone = row["ZONE_KEY"]
        period = "peak" if row["IS_PEAK"] else "offpeak"
        ratio = round(float(row["RATIO"]), 4)
        by_zone_period.setdefault(zone, {})[period] = ratio

    # --- by_zone ---
    bz = df.groupby("ZONE_KEY")["RATIO"].mean().reset_index()
    by_zone: dict = {
        row["ZONE_KEY"]: round(float(row["RATIO"]), 4)
        for _, row in bz.iterrows()
    }

    payload = {
        "by_zone_hour": {z: dict(sorted(h.items())) for z, h in sorted(by_zone_hour.items())},
        "by_zone_period": {z: v for z, v in sorted(by_zone_period.items())},
        "by_zone": dict(sorted(by_zone.items())),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        yaml.dump(payload, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Written: {OUTPUT_PATH}")
    print(f"  Zones: {len(by_zone)}")
    print(f"  Zone-hour entries: {sum(len(v) for v in by_zone_hour.values())}")


if __name__ == "__main__":
    main()
