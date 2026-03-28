"""
plotting.py — Reusable chart functions for the Rappi delivery analysis.
"""
from pathlib import Path
from typing import Optional, List

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

from src.config import FIGURES_DIR, FIGURE_DPI, FIGURE_SIZE, COLOR_PALETTE, PROJECT_ROOT

matplotlib.rcParams["figure.dpi"] = FIGURE_DPI


# ---------------------------------------------------------------------------
# Save helper
# ---------------------------------------------------------------------------

def _display_path(path: Path) -> str:
    """Prefer project-relative paths in notebook output."""
    path = Path(path)
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

def save_fig(fig: plt.Figure, name: str, dpi: int = FIGURE_DPI) -> None:
    """Save a figure to outputs/figures/<name>.png"""
    path = Path(FIGURES_DIR) / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    print(f"Figure saved → {_display_path(path)}")


# ---------------------------------------------------------------------------
# Distribution plots
# ---------------------------------------------------------------------------

def plot_distribution(
    series: pd.Series,
    title: str,
    log_scale: bool = False,
    figsize: tuple = FIGURE_SIZE,
) -> plt.Figure:
    """
    Histogram + boxplot side-by-side for a numeric series.
    """
    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Histogram
    axes[0].hist(series.dropna(), bins=40, color="steelblue", edgecolor="white", alpha=0.85)
    axes[0].set_title(f"{title} — Distribution")
    axes[0].set_xlabel(series.name or "value")
    axes[0].set_ylabel("Count")
    if log_scale:
        axes[0].set_yscale("log")

    # Boxplot
    axes[1].boxplot(series.dropna(), vert=True, patch_artist=True,
                    boxprops=dict(facecolor="steelblue", alpha=0.7))
    axes[1].set_title(f"{title} — Boxplot")
    axes[1].set_ylabel(series.name or "value")

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Hourly profile
# ---------------------------------------------------------------------------

def plot_hourly_profile(
    df: pd.DataFrame,
    metric: str,
    groupby: Optional[str] = None,
    agg: str = "mean",
    figsize: tuple = FIGURE_SIZE,
    title: Optional[str] = None,
) -> plt.Figure:
    """
    Line chart of avg (or other agg) metric by HOUR.
    If `groupby` is provided, one line per group.
    """
    fig, ax = plt.subplots(figsize=figsize)

    if groupby:
        for key, grp in df.groupby(groupby):
            hourly = grp.groupby("HOUR")[metric].agg(agg)
            ax.plot(hourly.index, hourly.values, marker="o", label=str(key))
        ax.legend(title=groupby, bbox_to_anchor=(1.01, 1), loc="upper left")
    else:
        hourly = df.groupby("HOUR")[metric].agg(agg)
        ax.plot(hourly.index, hourly.values, marker="o", color="steelblue")

    ax.set_xlabel("Hour of day")
    ax.set_ylabel(f"{agg.capitalize()} {metric}")
    ax.set_title(title or f"Hourly profile — {metric}")
    ax.set_xticks(range(0, 24))
    ax.grid(axis="y", alpha=0.4)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Heatmap (zone × hour or any pivot)
# ---------------------------------------------------------------------------

def plot_heatmap(
    pivot_df: pd.DataFrame,
    title: str = "Heatmap",
    cmap: str = "YlOrRd",
    fmt: str = ".2f",
    figsize: Optional[tuple] = None,
    annot: bool = True,
) -> plt.Figure:
    """
    Annotated seaborn heatmap from a pivot DataFrame.

    Parameters
    ----------
    pivot_df : DataFrame  e.g. zones as index, hours as columns
    """
    rows, cols = pivot_df.shape
    if figsize is None:
        figsize = (max(14, cols * 0.8), max(6, rows * 0.5))

    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        pivot_df,
        cmap=cmap,
        annot=annot,
        fmt=fmt,
        linewidths=0.3,
        ax=ax,
        cbar_kws={"shrink": 0.7},
    )
    ax.set_title(title, fontsize=13, pad=12)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Correlation matrix
# ---------------------------------------------------------------------------

def plot_correlation_matrix(
    df: pd.DataFrame,
    method: str = "pearson",
    cols: Optional[List[str]] = None,
    figsize: tuple = (8, 6),
    title: Optional[str] = None,
) -> plt.Figure:
    """
    Annotated correlation heatmap.

    Parameters
    ----------
    method : 'pearson' or 'spearman'
    cols   : subset of columns; None = all numeric
    """
    if cols:
        data = df[cols].copy()
    else:
        data = df.select_dtypes(include=[np.number])

    corr = data.corr(method=method)

    fig, ax = plt.subplots(figsize=figsize)
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)  # show lower triangle
    sns.heatmap(
        corr,
        mask=mask,
        cmap="coolwarm",
        vmin=-1,
        vmax=1,
        annot=True,
        fmt=".2f",
        linewidths=0.4,
        ax=ax,
        cbar_kws={"shrink": 0.8},
    )
    ax.set_title(title or f"{method.capitalize()} correlation matrix", fontsize=12)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Ranked bar chart
# ---------------------------------------------------------------------------

def plot_ranked_bar(
    series: pd.Series,
    title: str = "Ranked bar chart",
    top_n: int = 14,
    color: str = "steelblue",
    figsize: tuple = (10, 5),
) -> plt.Figure:
    """
    Horizontal bar chart of top_n values from a Series (sorted descending).
    """
    data = series.dropna().sort_values(ascending=True).tail(top_n)
    fig, ax = plt.subplots(figsize=figsize)
    data.plot(kind="barh", ax=ax, color=color, edgecolor="white")
    ax.set_title(title)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.2f}"))
    ax.grid(axis="x", alpha=0.4)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Bubble grid chart
# ---------------------------------------------------------------------------

def plot_bubble_grid(
    df: pd.DataFrame,
    x: str,
    y: str,
    size: str,
    color: Optional[str] = None,
    title: str = "Bubble chart",
    x_order: Optional[List] = None,
    y_order: Optional[List] = None,
    figsize: tuple = (14, 7),
    size_scale: float = 18.0,
    min_size: float = 12.0,
    cmap: str = "OrRd",
) -> plt.Figure:
    """
    Bubble chart over a discrete x/y grid.

    Typical use: zone x hour, where bubble size/color encode a percentage.
    """
    metric = color or size
    cols = [x, y, size] + ([] if metric == size else [metric])
    plot_df = df[cols].dropna().copy()

    if x_order is None:
        x_order = plot_df[x].drop_duplicates().tolist()
    if y_order is None:
        y_order = sorted(plot_df[y].drop_duplicates().tolist())

    x_map = {value: idx for idx, value in enumerate(x_order)}
    y_map = {value: idx for idx, value in enumerate(y_order)}

    plot_df["_x"] = plot_df[x].map(x_map)
    plot_df["_y"] = plot_df[y].map(y_map)

    values = plot_df[size].clip(lower=0)
    bubble_sizes = np.where(values > 0, values * size_scale + min_size, 0)

    fig, ax = plt.subplots(figsize=figsize)
    scatter = ax.scatter(
        plot_df["_x"],
        plot_df["_y"],
        s=bubble_sizes,
        c=plot_df[metric],
        cmap=cmap,
        alpha=0.85,
        edgecolors="white",
        linewidths=0.6,
    )

    ax.set_xticks(range(len(x_order)))
    ax.set_xticklabels(x_order, rotation=45, ha="right")
    ax.set_yticks(range(len(y_order)))
    ax.set_yticklabels(y_order)
    ax.set_xlabel(x.replace("_", " ").title())
    ax.set_ylabel(y.replace("_", " ").title())
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.set_axisbelow(True)

    cbar = fig.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label(metric.replace("_", " ").title())

    fig.tight_layout()
    return fig
