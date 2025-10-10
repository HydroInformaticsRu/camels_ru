"""Plotting functions for continuous (float) metrics on Russia maps.

This module extends the categorical mapping capabilities to support continuous
float-valued metrics with discrete colorbars and flexible subplot layouts.
"""

import math

import cartopy.crs as ccrs
import geopandas as gpd
from matplotlib import cm
from matplotlib.colors import BoundaryNorm
import matplotlib.pyplot as plt
import numpy as np


def _get_aea_crs() -> ccrs.AlbersEqualArea:
    """Return Albers Equal Area CRS for Russia."""
    return ccrs.AlbersEqualArea(
        central_longitude=100,
        standard_parallels=(50, 70),
        central_latitude=56,
        false_easting=0,
        false_northing=0,
    )


def _round_to_nice_value(value: float, is_min: bool = True) -> float:
    """Round value to nice colorbar limits (no rounding, use raw values).

    Args:
        value: Value to use.
        is_min: If True, for minimum; else for maximum.

    Returns:
        Original value (no rounding applied).
    """
    return float(value)


def _format_colorbar_label(value: float) -> str:
    """Format colorbar label to max 3 characters.

    Rules:
    - < 10: Keep to 1 decimal digit (0.56 -> "0.5", 9.24 -> "9.2")
    - 10-99: Keep to 1 decimal digit (12.34 -> "12.3")
    - >= 100: Round to nearest 5 or 0 ending (103 -> "105", 237 -> "235")

    Args:
        value: Value to format.

    Returns:
        Formatted string (max 3 characters).
    """
    abs_val = abs(value)

    if abs_val < 0.01:
        return "0"
    elif abs_val < 10.0:
        # Keep 1 decimal digit, max 3 chars (e.g., "0.5", "9.2")
        return f"{value:.1f}"
    elif abs_val < 100.0:
        # Keep 1 decimal digit if fits in 3 chars
        formatted = f"{value:.1f}"

        return formatted
    else:
        # Round to nearest 5 or 0 ending (103 -> 105, 237 -> 235)
        rounded = int(round(value / 5) * 5)
        return f"{rounded}"


def _add_histogram_inset(
    ax,
    gdf_data: gpd.GeoDataFrame,
    metric_col: str,
    bin_edges: np.ndarray,
    cmap,
    norm,
) -> None:
    """Add compact histogram inset below map (no background, no labels).

    Args:
        ax: Matplotlib axis to add histogram to.
        gdf_data: GeoDataFrame with data.
        metric_col: Column name for metric.
        bin_edges: Bin edges for histogram.
        cmap: Colormap.
        norm: Normalization.
    """
    values = gdf_data[metric_col].dropna()
    if len(values) == 0:
        return

    # Create histogram data
    hist, _ = np.histogram(values, bins=bin_edges)

    ax_hist = ax.inset_axes([0.15, 0.03, 0.70, 0.10])

    # Create bars with matching colors
    bar_colors = [cmap(norm((bin_edges[i] + bin_edges[i + 1]) / 2)) for i in range(len(hist))]

    bars = ax_hist.bar(
        range(len(hist)),
        hist,
        width=0.95,
        color=bar_colors,
        edgecolor="black",
        linewidth=0.5,
    )

    # Add count labels on bars
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax_hist.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{int(height)}",
                ha="center",
                va="bottom",
                fontsize=6,
            )

    # Remove all labels and background
    ax_hist.set_xticks([])
    ax_hist.set_yticks([])
    ax_hist.set_xlabel("")
    ax_hist.set_ylabel("")
    ax_hist.spines["top"].set_visible(False)
    ax_hist.spines["right"].set_visible(False)
    ax_hist.spines["bottom"].set_visible(False)
    ax_hist.spines["left"].set_visible(False)
    ax_hist.patch.set_visible(False)  # Remove background


def russia_continuous_plot(
    gdf_to_plot: gpd.GeoDataFrame,
    basemap_data: gpd.GeoDataFrame,
    metric_col: str,
    title_text: str = "",
    rus_extent: list | None = None,
    n_bins: int = 6,
    cmap_name: str = "RdYlGn",
    figsize: tuple = (4.88189, 3.34646),
    vmin: float | None = None,
    vmax: float | None = None,
) -> plt.Figure:
    """Plot Russia map with continuous metric using discrete colorbar.

    Args:
        gdf_to_plot: GeoDataFrame with points to plot (must have geometry).
        basemap_data: GeoDataFrame with basemap polygons.
        metric_col: Column name containing continuous metric values.
        title_text: Plot title.
        rus_extent: Extent [lon_min, lon_max, lat_min, lat_max] for plot.
        n_bins: Number of discrete bins for colorbar (default 6).
        cmap_name: Matplotlib colormap name.
        figsize: Figure size (width, height) in inches.
        vmin: Minimum value for color scale (auto if None).
        vmax: Maximum value for color scale (auto if None).

    Returns:
        Matplotlib figure object.
    """
    aea_crs = _get_aea_crs()
    aea_crs_proj4 = aea_crs.proj4_init

    if rus_extent is None:
        rus_extent = [19.5, 180, 41.5, 82]

    # Convert to projected CRS
    gdf_proj = gdf_to_plot.to_crs(aea_crs_proj4)
    basemap_proj = basemap_data.to_crs(aea_crs_proj4)

    # Extract metric values and compute bins
    values = gdf_proj[metric_col].dropna()
    if len(values) == 0:
        raise ValueError(f"No valid values in column '{metric_col}'")

    if vmin is None:
        vmin = float(values.min())
    if vmax is None:
        vmax = float(values.max())

    # Create discrete bins
    bin_edges = np.linspace(vmin, vmax, n_bins + 1)
    norm = BoundaryNorm(bin_edges, n_bins)
    cmap = cm.get_cmap(cmap_name, n_bins)

    # Create figure
    fig, ax = plt.subplots(figsize=figsize, subplot_kw={"projection": aea_crs})
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_extent(rus_extent)  # type: ignore

    # Plot basemap
    basemap_proj.plot(ax=ax, color="grey", edgecolor="black", alpha=0.8, legend=False)

    # Plot points with continuous colormap
    scatter = gdf_proj.plot(
        ax=ax,
        column=metric_col,
        cmap=cmap,
        norm=norm,
        marker="o",
        markersize=24,
        edgecolor="black",
        linewidth=0.2,
        legend=True,
        legend_kwds={
            "orientation": "horizontal",
            "shrink": 0.35,
            "pad": 0.02,
            "anchor": (0.6, 0.5),
            "label": metric_col,
        },
    )

    ax.set_title(title_text, fontdict={"size": 12})
    plt.tight_layout()

    return fig


def russia_continuous_multiplot(
    gdf_to_plot: gpd.GeoDataFrame,
    basemap_data: gpd.GeoDataFrame,
    metrics: list[str],
    titles: list[str] | None = None,
    main_title: str = "",
    rus_extent: list | None = None,
    n_bins: int = 6,
    cmap_name: str = "RdYlGn",
    ncols: int = 3,
    subplot_size: tuple = (6.0, 4.5),
    vmin_dict: dict[str, float] | None = None,
    vmax_dict: dict[str, float] | None = None,
    with_histogram: bool = True,
    marker_size: int = 18,
) -> plt.Figure:
    """Create multipanel plot with continuous metrics.

    Automatically calculates optimal subplot layout based on number of metrics.

    Args:
        gdf_to_plot: GeoDataFrame with points to plot.
        basemap_data: GeoDataFrame with basemap polygons.
        metrics: List of column names to plot.
        titles: Optional list of titles for each subplot.
        main_title: Overall figure title.
        rus_extent: Extent for Russia map.
        n_bins: Number of discrete bins per colorbar.
        cmap_name: Matplotlib colormap name.
        ncols: Number of columns in subplot grid.
        subplot_size: Size (width, height) of each subplot.
        vmin_dict: Optional dict mapping metric name to minimum value.
        vmax_dict: Optional dict mapping metric name to maximum value.
        with_histogram: Whether to add histogram inset (default True).
        marker_size: Size of point markers (default 18).

    Returns:
        Matplotlib figure object.
    """
    n_metrics = len(metrics)
    if n_metrics == 0:
        raise ValueError("No metrics provided")

    # Calculate subplot grid
    nrows = math.ceil(n_metrics / ncols)

    # Use default titles if not provided
    if titles is None:
        titles = metrics

    if len(titles) != n_metrics:
        raise ValueError("Number of titles must match number of metrics")

    # Initialize min/max dicts if not provided
    vmin_dict = vmin_dict or {}
    vmax_dict = vmax_dict or {}

    # Setup CRS
    aea_crs = _get_aea_crs()
    aea_crs_proj4 = aea_crs.proj4_init

    if rus_extent is None:
        rus_extent = [19.5, 180, 41.5, 82]

    # Convert to projected CRS once
    gdf_proj = gdf_to_plot.to_crs(aea_crs_proj4)
    basemap_proj = basemap_data.to_crs(aea_crs_proj4)

    # Create figure with subplots
    fig_width = subplot_size[0] * ncols
    fig_height = subplot_size[1] * nrows
    fig = plt.figure(figsize=(fig_width, fig_height))

    for idx, (metric, title) in enumerate(zip(metrics, titles, strict=False)):
        # Create subplot with projection
        ax = fig.add_subplot(nrows, ncols, idx + 1, projection=aea_crs)
        ax.set_aspect("auto")
        ax.axis("off")
        ax.set_extent(rus_extent, crs=ccrs.PlateCarree())

        # Plot basemap with better visibility
        basemap_proj.plot(
            ax=ax, color="#E5E5E5", edgecolor="#404040", linewidth=0.5, alpha=1.0, legend=False
        )

        # Get values and determine range
        values = gdf_proj[metric].dropna()

        # Get value range and round to nice limits
        raw_vmin = vmin_dict.get(metric, float(values.min()))
        raw_vmax = vmax_dict.get(metric, float(values.max()))

        vmin = _round_to_nice_value(raw_vmin, is_min=True)
        vmax = _round_to_nice_value(raw_vmax, is_min=False)

        # Ensure vmin < vmax
        if vmin >= vmax:
            vmax = vmin + 0.1

        # Create discrete bins
        bin_edges = np.linspace(vmin, vmax, n_bins + 1)
        norm = BoundaryNorm(bin_edges, n_bins)
        cmap = cm.get_cmap(cmap_name, n_bins)

        # Plot points with improved visibility
        gdf_proj.plot(
            ax=ax,
            column=metric,
            cmap=cmap,
            norm=norm,
            marker="o",
            markersize=marker_size,
            edgecolor="black",
            linewidth=0.25,
            legend=True,
            legend_kwds={
                "orientation": "horizontal",
                "shrink": 0.70,
                "pad": 0.09,
                "aspect": 35,
                "anchor": (0.5, 1.0),
                "panchor": (0.5, 0.0),
                "label": "",
            },
            missing_kwds={"color": "lightgrey", "edgecolor": "red", "label": "Missing"},
        )

        # Format colorbar ticks - get the colorbar from most recent plot
        if len(fig.axes) > idx + 1:
            cbar_ax = fig.axes[-1]
            if hasattr(cbar_ax, "get_ylabel") or "colorbar" in str(type(cbar_ax)):
                # Format tick labels with proper rounding
                tick_locs = bin_edges
                tick_labels = [_format_colorbar_label(val) for val in tick_locs]
                cbar_ax.set_xticks(tick_locs)
                cbar_ax.set_xticklabels(tick_labels, fontsize=7)
                cbar_ax.tick_params(labelsize=7, length=3, width=0.5)

        # Add histogram if requested
        if with_histogram:
            _add_histogram_inset(ax, gdf_proj, metric, bin_edges, cmap, norm)

        ax.set_title(title, fontdict={"size": 11, "weight": "normal"}, pad=8)

    # Add main title with better spacing
    if main_title:
        fig.suptitle(main_title, fontsize=15, y=0.99, weight="bold")

    # Adjust layout with more space for colorbars
    plt.tight_layout(rect=[0, 0.01, 1, 0.97] if main_title else [0, 0.01, 1, 1])

    return fig
