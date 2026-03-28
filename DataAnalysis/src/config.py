"""
config.py — Central constants and paths for the Rappi delivery analysis project.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root (one level above this file)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_PATH = PROJECT_ROOT / "data" / "rappi_delivery_case_data.xlsx"

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
OUTPUTS_DIR   = PROJECT_ROOT / "outputs"
CLEANED_DIR   = OUTPUTS_DIR / "cleaned"
FIGURES_DIR   = OUTPUTS_DIR / "figures"
TABLES_DIR    = OUTPUTS_DIR / "tables"

# Cleaned data filenames
RAW_CLEAN_PATH      = CLEANED_DIR / "raw_data_clean.parquet"
ZONE_INFO_CLEAN_PATH = CLEANED_DIR / "zone_info_clean.parquet"
POLYGONS_CLEAN_PATH  = CLEANED_DIR / "zone_polygons_clean.parquet"

# ---------------------------------------------------------------------------
# Saturation thresholds  (from the Rappi case document)
# RATIO = ORDERS / CONNECTED_RT
# ---------------------------------------------------------------------------
RATIO_OVER_SUPPLY  = 0.5   # < 0.5  → over-supply / cost inefficiency
RATIO_LOW          = 0.9   # 0.5–0.9 → below healthy
RATIO_HEALTHY_LOW  = 0.9   # 0.9–1.2 → healthy range
RATIO_HEALTHY_HIGH = 1.2
RATIO_HIGH         = 1.8   # 1.2–1.8 → high utilisation
RATIO_SATURATION   = 1.8   # > 1.8  → SATURATION (order loss)

SATURATION_LABELS = {
    "over_supply":      (None, RATIO_OVER_SUPPLY),
    "low_utilization":  (RATIO_OVER_SUPPLY, RATIO_LOW),
    "healthy":          (RATIO_HEALTHY_LOW, RATIO_HEALTHY_HIGH),
    "high_utilization": (RATIO_HEALTHY_HIGH, RATIO_HIGH),
    "saturation":       (RATIO_SATURATION, None),
}

# ---------------------------------------------------------------------------
# Rain bucket thresholds  (mm/hr, compatible with Open-Meteo)
# ---------------------------------------------------------------------------
RAIN_NONE     = 0.0
RAIN_LIGHT    = 0.1   # 0.0 → no rain;  0.1–2.0 → light
RAIN_MODERATE = 2.0   # 2.0–5.0 → moderate
RAIN_HEAVY    = 5.0   # > 5.0   → heavy

RAIN_BUCKET_BINS   = [RAIN_NONE, RAIN_LIGHT, RAIN_MODERATE, RAIN_HEAVY, float("inf")]
RAIN_BUCKET_LABELS = ["no_rain", "light", "moderate", "heavy"]

# ---------------------------------------------------------------------------
# Plotting defaults
# ---------------------------------------------------------------------------
FIGURE_DPI    = 120
FIGURE_SIZE   = (12, 5)
COLOR_PALETTE = "tab10"
