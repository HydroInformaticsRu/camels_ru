"""Border-free plotting for ESSD Paper 1 figures.

Lightweight spatial plotting using raw geographic coordinates (lon/lat)
with latitude-corrected aspect ratio. No Cartopy, no basemap dependency.

Matches the pattern established in notebooks 00_DataDescription.py and
01_HydroAtlasFinal.py:
  - Plain matplotlib scatter on unprojected lon/lat
  - Aspect correction: 1 / cos(55°) for Russia's center latitude
  - Colorblind-safe Paul Tol palette
  - Grid with alpha=0.15, linestyle="--"

Usage
-----
>>> from src.plots.paper_maps import continuous_multiplot, categorical_map
>>> fig = continuous_multiplot(gdf, ["bfi", "q_mean"], ["BFI", "Mean Q"])
>>> fig = categorical_map(gdf, ax, "cluster", palette=PAUL_TOL_BRIGHT)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import geopandas as gpd
from matplotlib import cm
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# Russia center latitude for aspect correction
_CENTER_LAT = 55.0
_ASPECT = 1.0 / np.cos(np.radians(_CENTER_LAT))

# Paul Tol bright palette (colorblind-safe, up to 7 distinct colors)
PAUL_TOL_BRIGHT: list[str] = [
    "#4477AA",  # blue
    "#EE6677",  # pink/red
    "#228833",  # green
    "#CCBB44",  # yellow
    "#66CCEE",  # cyan
    "#AA3377",  # purple
    "#BBBBBB",  # grey
]

# Extended palette: Paul Tol vibrant + muted for 15+ categories
PAUL_TOL_EXTENDED: list[str] = [
    "#4477AA",
    "#EE6677",
    "#228833",
    "#CCBB44",
    "#66CCEE",
    "#AA3377",
    "#EE7733",
    "#0077BB",
    "#33BBEE",
    "#EE3377",
    "#009988",
    "#CC3311",
    "#882255",
    "#44BB99",
    "#DDCC77",
]

# Default markers for categorical maps (15 distinct shapes)
_MARKERS: list[str] = [
    "o",
    "s",
    "^",
    "v",
    "D",
    "<",
    ">",
    "P",
    "X",
    "*",
    "h",
    "p",
    "d",
    "H",
    "8",
]


def _apply_map_style(
    ax: Axes,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> None:
    """Apply consistent map styling to an axis."""
    ax.set_xlabel("Longitude (°E)", fontsize=11)
    ax.set_ylabel("Latitude (°N)", fontsize=11)
    ax.tick_params(labelsize=10)
    ax.set_aspect(_ASPECT)
    ax.grid(alpha=0.15, linestyle="--")
    if xlim is not None:
        ax.set_xlim(xlim)
    if ylim is not None:
        ax.set_ylim(ylim)


def _auto_bins(values: np.ndarray, n_bins: int = 6) -> np.ndarray:
    """Generate evenly-spaced bin edges from data range."""
    vmin, vmax = float(np.nanmin(values)), float(np.nanmax(values))
    if vmin >= vmax:
        vmax = vmin + 1.0
    return np.linspace(vmin, vmax, n_bins + 1)


def scatter_map(
    gdf: gpd.GeoDataFrame,
    ax: Axes,
    color_col: str,
    *,
    cmap_name: str = "RdYlBu_r",
    bin_edges: np.ndarray | list[float] | None = None,
    n_bins: int = 6,
    marker_size: int = 10,
    title: str = "",
    show_nan: bool = True,
    nan_size: int = 3,
    colorbar: bool = True,
    colorbar_label: str = "",
    colorbar_orientation: str = "horizontal",
    background_gdf: gpd.GeoDataFrame | None = None,
) -> Axes:
    """Plot continuous-valued scatter map on a single axis.

    Parameters
    ----------
    gdf : GeoDataFrame
        Must have point geometry and a numeric column *color_col*.
    ax : Axes
        Matplotlib axis to plot on.
    color_col : str
        Column name for the color mapping.
    cmap_name : str
        Matplotlib colormap name.
    bin_edges : array-like, optional
        Custom bin edges for BoundaryNorm. Auto-generated if None.
    n_bins : int
        Number of bins when auto-generating edges.
    marker_size : int
        Scatter marker size.
    title : str
        Subplot title.
    show_nan : bool
        Show NaN values as tiny grey dots.
    nan_size : int
        Marker size for NaN points.
    colorbar : bool
        Whether to add a colorbar.
    colorbar_label : str
        Label for the colorbar.
    colorbar_orientation : str
        "horizontal" or "vertical".

    Returns:
    -------
    Axes
    """
    # Draw background landmass if provided
    if background_gdf is not None:
        background_gdf.plot(
            ax=ax,
            color="#EDEDED",
            edgecolor="#CCCCCC",
            linewidth=0.3,
            zorder=1,
        )

    valid = gdf[gdf[color_col].notna()].copy()
    nan_mask = gdf[color_col].isna()

    values = np.asarray(valid[color_col])
    edges = np.asarray(bin_edges) if bin_edges is not None else _auto_bins(values, n_bins)
    n = len(edges) - 1
    norm = BoundaryNorm(edges, n)
    cmap = cm.get_cmap(cmap_name, n)

    if not valid.empty:
        sc = ax.scatter(
            valid.geometry.x,
            valid.geometry.y,
            c=values,
            cmap=cmap,
            norm=norm,
            s=marker_size,
            edgecolors="none",
            zorder=3,
        )
        if colorbar:
            cb = ax.figure.colorbar(  # type: ignore[union-attr]
                sc,
                ax=ax,
                orientation=colorbar_orientation,
                shrink=0.7,
                pad=0.12 if colorbar_orientation == "horizontal" else 0.04,
                aspect=25,
            )
            cb.set_ticks(edges.tolist())
            # Clean numeric labels: no scientific notation, no trailing zeros
            labels = []
            for v in edges:
                if v == 0:
                    labels.append("0")
                elif v == int(v) and abs(v) >= 1:
                    labels.append(f"{int(v)}")
                else:
                    labels.append(f"{v:g}")
            cb.set_ticklabels(labels)
            cb.ax.tick_params(labelsize=9)
            if colorbar_label:
                cb.set_label(colorbar_label, fontsize=10)

    if show_nan and bool(nan_mask.any()):
        nan_gdf = gdf[nan_mask]
        ax.scatter(
            nan_gdf.geometry.x,
            nan_gdf.geometry.y,
            s=nan_size,
            c="#BBBBBB",
            marker=".",
            edgecolors="none",
            zorder=2,
            alpha=0.5,
        )

    if title:
        ax.set_title(title, fontsize=12, fontweight="bold", loc="left")

    # Set axis limits from data extent with buffer
    all_x = gdf.geometry.x
    all_y = gdf.geometry.y
    x_buf = (all_x.max() - all_x.min()) * 0.05
    y_buf = (all_y.max() - all_y.min()) * 0.08
    _apply_map_style(
        ax,
        xlim=(all_x.min() - x_buf, all_x.max() + x_buf),
        ylim=(all_y.min() - y_buf, all_y.max() + y_buf),
    )
    return ax


def continuous_multiplot(
    gdf: gpd.GeoDataFrame,
    metrics: list[str],
    titles: list[str] | None = None,
    *,
    ncols: int = 4,
    panel_size: tuple[float, float] = (4.0, 3.0),
    cmap_name: str = "RdYlBu_r",
    bin_intervals: dict[str, list[float]] | None = None,
    n_bins: int = 6,
    marker_size: int = 8,
    suptitle: str = "",
    show_nan: bool = True,
    colorbar_labels: dict[str, str] | None = None,
    background_gdf: gpd.GeoDataFrame | None = None,
) -> Figure:
    """Create N-panel scatter maps with colorbars for continuous metrics.

    Parameters
    ----------
    gdf : GeoDataFrame
        Point geometry with numeric columns for each metric.
    metrics : list[str]
        Column names to plot (one per panel).
    titles : list[str], optional
        Panel titles. Defaults to metric names.
    ncols : int
        Number of columns in the subplot grid.
    panel_size : tuple
        (width, height) per panel in inches.
    cmap_name : str
        Matplotlib colormap name.
    bin_intervals : dict, optional
        Custom bin edges per metric: {"metric_name": [edge0, edge1, ...]}.
    n_bins : int
        Default number of bins when no custom edges provided.
    marker_size : int
        Scatter marker size.
    suptitle : str
        Overall figure title.
    show_nan : bool
        Show NaN values as grey dots.
    colorbar_labels : dict, optional
        Per-metric colorbar labels.

    Returns:
    -------
    Figure
    """
    n = len(metrics)
    if n == 0:
        raise ValueError("No metrics provided")

    titles_use = titles if titles is not None else metrics
    if len(titles_use) != n:
        raise ValueError("len(titles) must match len(metrics)")

    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(panel_size[0] * ncols, panel_size[1] * nrows),
        squeeze=False,
        constrained_layout=True,
    )

    bin_intervals = bin_intervals or {}
    colorbar_labels = colorbar_labels or {}

    for idx, (metric, title) in enumerate(zip(metrics, titles_use, strict=True)):
        row, col = divmod(idx, ncols)
        ax = axes[row, col]

        edges = bin_intervals.get(metric)
        cb_label = colorbar_labels.get(metric, "")

        scatter_map(
            gdf,
            ax,
            metric,
            cmap_name=cmap_name,
            bin_edges=edges,
            n_bins=n_bins,
            marker_size=marker_size,
            title=title,
            show_nan=show_nan,
            colorbar_label=cb_label,
            background_gdf=background_gdf,
        )

    # Hide unused axes
    for idx in range(n, nrows * ncols):
        row, col = divmod(idx, ncols)
        axes[row, col].set_visible(False)

    if suptitle:
        fig.suptitle(suptitle, fontsize=14, fontweight="bold")

    return fig


def categorical_map(
    gdf: gpd.GeoDataFrame,
    ax: Axes,
    cat_col: str,
    *,
    palette: list[str] | None = None,
    markers: list[str] | None = None,
    category_order: list | None = None,
    marker_size: int = 12,
    title: str = "",
    legend_ncol: int = 5,
    legend_fontsize: float = 6,
    legend_loc: str = "lower right",
    show_counts: bool = True,
) -> Axes:
    """Plot scatter map with categorical colors and legend.

    Parameters
    ----------
    gdf : GeoDataFrame
        Point geometry with a categorical column *cat_col*.
    ax : Axes
        Matplotlib axis.
    cat_col : str
        Column with category labels.
    palette : list[str], optional
        Colors per category. Defaults to PAUL_TOL_EXTENDED.
    markers : list[str], optional
        Marker shapes per category. Defaults to varied shapes.
    category_order : list, optional
        Explicit category order. Defaults to sorted unique values.
    marker_size : int
        Scatter marker size.
    title : str
        Subplot title.
    legend_ncol : int
        Legend columns.
    legend_fontsize : float
        Legend text size.
    legend_loc : str
        Legend location string.
    show_counts : bool
        Append "(n=X)" to legend labels.

    Returns:
    -------
    Axes
    """
    colors = palette or PAUL_TOL_EXTENDED
    mkrs = markers or _MARKERS

    cats = (
        category_order if category_order is not None else sorted(gdf[cat_col].dropna().unique(), key=str)
    )

    handles = []
    for i, cat in enumerate(cats):
        subset = gdf[gdf[cat_col] == cat]
        if subset.empty:
            continue

        c = colors[i % len(colors)]
        m = mkrs[i % len(mkrs)]

        ax.scatter(
            subset.geometry.x,
            subset.geometry.y,
            c=c,
            marker=m,
            s=marker_size,
            alpha=0.7,
            edgecolors="none",
            zorder=3,
        )

        label = f"{cat} (n={len(subset)})" if show_counts else str(cat)
        handles.append(
            Line2D(
                [],
                [],
                marker=m,
                color="none",
                markerfacecolor=c,
                markeredgecolor="none",
                markersize=5,
                linestyle="None",
                label=label,
            )
        )

    if handles:
        ax.legend(
            handles=handles,
            fontsize=legend_fontsize,
            ncol=legend_ncol,
            loc=legend_loc,
            framealpha=0.9,
            handletextpad=0.2,
            columnspacing=0.5,
            edgecolor="0.8",
        )

    if title:
        ax.set_title(title, fontsize=10, fontweight="bold", loc="left")

    _apply_map_style(ax)
    return ax
