"""
io_utils.py — Load and save helpers for the Rappi delivery analysis project.
"""
from pathlib import Path
from typing import Dict

import pandas as pd

from src.config import (
    DATA_PATH,
    CLEANED_DIR,
    PROJECT_ROOT,
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_all_sheets(path: Path = DATA_PATH) -> Dict[str, pd.DataFrame]:
    """
    Read ALL sheets from the workbook into a dictionary of DataFrames.
    Sheet names are taken directly from the Excel file — nothing is hardcoded.
    Column names are stripped of leading/trailing whitespace.

    Returns
    -------
    dict mapping actual sheet name → DataFrame for every sheet in the file.
    """
    xl = pd.ExcelFile(path, engine="openpyxl")
    sheets = {}
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        df.columns = [str(c).strip() for c in df.columns]
        sheets[sheet] = df
    return sheets


def load_cleaned(name: str) -> pd.DataFrame:
    """
    Load a cleaned parquet file from outputs/cleaned/.

    Parameters
    ----------
    name : str  e.g. "raw_data_clean", "zone_info_clean", "zone_polygons_clean"
    """
    path = CLEANED_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Cleaned file not found: {path}\n"
            "Run notebook 01 first to produce cleaned outputs."
        )
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def _display_path(path: Path) -> str:
    """Prefer project-relative paths in notebook output."""
    path = Path(path)
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

def save_parquet(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame as parquet, creating parent directories if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"Saved parquet → {_display_path(path)}  ({len(df):,} rows)")


def save_csv(df: pd.DataFrame, path: Path, **kwargs) -> None:
    """Save a DataFrame as CSV, creating parent directories if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, **kwargs)
    print(f"Saved CSV    → {_display_path(path)}  ({len(df):,} rows)")

# ---------------------------------------------------------------------------
# Print
# ---------------------------------------------------------------------------

def print_sheet_summary(sheets: Dict[str, pd.DataFrame]) -> None:
    """Print a quick shape/dtype overview for all loaded sheets."""
    for name, df in sheets.items():
        print(f"\n{'='*60}")
        print(f"Sheet : {name}")
        print(f"Shape : {df.shape[0]:,} rows × {df.shape[1]} columns")
        print(f"Columns: {list(df.columns)}")
        print(df.dtypes.to_string())
        print(f"\nFirst 3 rows:\n{df.head(3).to_string()}")
