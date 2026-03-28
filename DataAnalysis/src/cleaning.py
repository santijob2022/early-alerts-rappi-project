"""
cleaning.py — Data-type standardisation, feature derivation, and anomaly flagging.
"""
import unicodedata
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Type standardisation
# ---------------------------------------------------------------------------

def standardize_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coerce columns to expected types without losing rows silently.

    Changes
    -------
    - DATE            → datetime64[ns]       (coerce errors → NaT)
    - HOUR            → Int64 (nullable int) (coerce errors → NA)
    - CONNECTED_RT    → float64              (coerce errors → NaN)
    - ORDERS          → float64
    - EARNINGS        → float64
    - PRECIPITATION_MM → float64
    - Text columns    → stripped strings
    """
    df = df.copy()

    # Date
    if "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    # Integer columns
    for col in ["HOUR"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Numeric measures
    for col in ["CONNECTED_RT", "ORDERS", "EARNINGS", "PRECIPITATION_MM"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Text normalisation
    for col in ["COUNTRY", "CITY", "ZONE", "DESCRIPTION", "ZONE_NAME"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


# ---------------------------------------------------------------------------
# Derived time features
# ---------------------------------------------------------------------------

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived temporal columns from DATE and HOUR.

    New columns
    -----------
    DAY_OF_WEEK   : int  (0=Monday … 6=Sunday)
    DAY_NAME      : str  e.g. "Monday"
    MONTH         : int  (1–12)
    IS_WEEKEND    : bool (True for Saturday/Sunday)
    DATETIME      : datetime64[ns]  (DATE + HOUR as timedelta)
    """
    df = df.copy()

    if "DATE" not in df.columns:
        return df

    df["DAY_OF_WEEK"] = df["DATE"].dt.dayofweek
    df["DAY_NAME"]    = df["DATE"].dt.day_name()
    df["MONTH"]       = df["DATE"].dt.month
    df["IS_WEEKEND"]  = df["DAY_OF_WEEK"].isin([5, 6])

    if "HOUR" in df.columns:
        hour_td = pd.to_timedelta(df["HOUR"].fillna(0).astype(int), unit="h")
        df["DATETIME"] = df["DATE"] + hour_td

    return df


# ---------------------------------------------------------------------------
# Join-key normalisation
# ---------------------------------------------------------------------------

def _remove_accents(text: str) -> str:
    """Strip diacritics from a Unicode string."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clean_text_key(series: pd.Series) -> pd.Series:
    """
    Produce a normalised, comparable text key for zone name matching.

    Transformations applied
    -----------------------
    1. Convert to string
    2. Strip leading/trailing whitespace
    3. Collapse internal multiple spaces → single space
    4. Convert to UPPERCASE
    5. Remove diacritics/accents
    """
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.upper()
        .apply(_remove_accents)
    )


# ---------------------------------------------------------------------------
# Invalid-row flagging
# ---------------------------------------------------------------------------

def flag_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a boolean column IS_INVALID and a text column INVALID_REASON
    for rows that fail basic sanity checks.

    Checks
    ------
    - HOUR outside [0, 23]
    - ORDERS < 0
    - CONNECTED_RT < 0
    - PRECIPITATION_MM < 0
    - ZONE is blank, null, or literal "nan"
    - CITY is blank, null, or literal "nan"
    """
    df = df.copy()
    reasons = pd.Series([""] * len(df), index=df.index)

    if "HOUR" in df.columns:
        mask = df["HOUR"].notna() & ~df["HOUR"].between(0, 23)
        reasons[mask] += "HOUR_INVALID;"

    for col in ["ORDERS", "CONNECTED_RT", "PRECIPITATION_MM"]:
        if col in df.columns:
            mask = df[col].notna() & (df[col] < 0)
            reasons[mask] += f"{col}_NEGATIVE;"

    for col in ["ZONE", "CITY"]:
        if col in df.columns:
            mask = df[col].isin(["", "nan", "None"]) | df[col].isna()
            reasons[mask] += f"{col}_BLANK;"

    df["IS_INVALID"]    = reasons.str.len() > 0
    df["INVALID_REASON"] = reasons.str.rstrip(";")
    return df


# ---------------------------------------------------------------------------
# Whitespace / name standardisation for lookup tables
# ---------------------------------------------------------------------------

def standardize_lookup(df: pd.DataFrame, text_cols: list) -> pd.DataFrame:
    """Strip whitespace and add _CLEAN key columns for merging."""
    df = df.copy()
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[f"{col}_CLEAN"] = clean_text_key(df[col])
    return df
