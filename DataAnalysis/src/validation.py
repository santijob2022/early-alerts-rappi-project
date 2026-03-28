"""
validation.py — Grain checks, key uniqueness, zone coverage, and merge cardinality.
"""
from typing import List

import pandas as pd


# ---------------------------------------------------------------------------
# Grain validation
# ---------------------------------------------------------------------------

def check_grain(df: pd.DataFrame, keys: List[str]) -> pd.DataFrame:
    """
    Test whether `keys` uniquely identify every row in `df`.

    Returns
    -------
    DataFrame of duplicate rows (empty = grain is valid).

    Usage
    -----
    dupes = check_grain(raw, ["COUNTRY", "DATE", "HOUR", "CITY", "ZONE"])
    if dupes.empty:
        print("Grain is valid.")
    """
    missing = [k for k in keys if k not in df.columns]
    if missing:
        raise ValueError(f"Keys not found in DataFrame: {missing}")

    dupes = df[df.duplicated(subset=keys, keep=False)].copy()
    n_dupes = dupes.shape[0]

    if n_dupes == 0:
        print(f"✓ Grain valid — all {len(keys)}-key combinations are unique.")
    else:
        print(
            f"✗ Grain INVALID — {n_dupes:,} rows share a duplicate key "
            f"({n_dupes / len(df):.1%} of table)."
        )

    return dupes


# ---------------------------------------------------------------------------
# Key uniqueness in lookup / dimension tables
# ---------------------------------------------------------------------------

def check_key_uniqueness(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """
    Verify that `col` has no duplicated values.

    Returns
    -------
    DataFrame of duplicated values (empty = column is unique).
    """
    if col not in df.columns:
        raise ValueError(f"Column '{col}' not found.")

    dupes = df[df.duplicated(subset=[col], keep=False)][[col]].value_counts().reset_index()
    dupes.columns = [col, "count"]

    if dupes.empty:
        print(f"✓ '{col}' is unique — no duplicate values found.")
    else:
        print(f"✗ '{col}' has {len(dupes)} duplicated values:")
        print(dupes.to_string(index=False))

    return dupes


# ---------------------------------------------------------------------------
# Zone coverage comparison
# ---------------------------------------------------------------------------

def compare_zone_sets(
    raw: pd.DataFrame,
    zone_info: pd.DataFrame,
    zone_polygons: pd.DataFrame,
    raw_col: str = "ZONE_CLEAN",
    info_col: str = "ZONE_CLEAN",
    poly_col: str = "ZONE_CLEAN",
) -> dict:
    """
    Compare distinct zone sets across the three tables.

    Returns
    -------
    dict with keys:
        raw_zones            : set of zones in RAW_DATA
        info_zones           : set of zones in ZONE_INFO
        polygon_zones        : set of zones in ZONE_POLYGONS
        in_raw_not_info      : zones present in RAW but missing in ZONE_INFO
        in_raw_not_polygons  : zones present in RAW but missing in ZONE_POLYGONS
        in_info_not_raw      : orphan zones in ZONE_INFO
        in_polygons_not_raw  : orphan zones in ZONE_POLYGONS
        full_match           : bool
    """
    raw_z  = set(raw[raw_col].dropna().unique()) if raw_col in raw.columns else set()
    info_z = set(zone_info[info_col].dropna().unique()) if info_col in zone_info.columns else set()
    poly_z = set(zone_polygons[poly_col].dropna().unique()) if poly_col in zone_polygons.columns else set()

    result = {
        "raw_zones":           raw_z,
        "info_zones":          info_z,
        "polygon_zones":       poly_z,
        "in_raw_not_info":     raw_z - info_z,
        "in_raw_not_polygons": raw_z - poly_z,
        "in_info_not_raw":     info_z - raw_z,
        "in_polygons_not_raw": poly_z - raw_z,
        "full_match":          (raw_z == info_z) and (raw_z == poly_z),
    }

    print(f"RAW_DATA zones     : {len(raw_z)}")
    print(f"ZONE_INFO zones    : {len(info_z)}")
    print(f"ZONE_POLYGONS zones: {len(poly_z)}")
    print(f"In RAW not in ZONE_INFO    : {result['in_raw_not_info']}")
    print(f"In RAW not in POLYGONS     : {result['in_raw_not_polygons']}")
    print(f"Orphans in ZONE_INFO       : {result['in_info_not_raw']}")
    print(f"Orphans in ZONE_POLYGONS   : {result['in_polygons_not_raw']}")
    print(f"Full match across all sheets: {result['full_match']}")

    return result


# ---------------------------------------------------------------------------
# Merge cardinality check
# ---------------------------------------------------------------------------

def validate_merge_cardinality(
    left: pd.DataFrame,
    right: pd.DataFrame,
    key: str,
) -> str:
    """
    Determine expected merge relationship between left and right tables.

    Returns one of: 'one-to-one', 'many-to-one', 'one-to-many', 'many-to-many'.
    Also prints a warning for many-to-many which should stop the merge.
    """
    left_unique  = left[key].nunique()  == len(left)
    right_unique = right[key].nunique() == len(right)

    if left_unique and right_unique:
        rel = "one-to-one"
    elif not left_unique and right_unique:
        rel = "many-to-one"
    elif left_unique and not right_unique:
        rel = "one-to-many"
    else:
        rel = "many-to-many"

    print(f"Left  '{key}' unique: {left_unique}  ({left[key].nunique()} unique / {len(left)} rows)")
    print(f"Right '{key}' unique: {right_unique}  ({right[key].nunique()} unique / {len(right)} rows)")
    print(f"→ Merge relationship: {rel}")

    if rel == "many-to-many":
        print("⚠️  WARNING: many-to-many merge will multiply rows. Resolve duplicates before merging.")

    return rel
