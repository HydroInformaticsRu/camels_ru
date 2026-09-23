"""Fixed-origin pointy-top hexagons for outlet-supported manuscript summaries."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import Polygon


def assign_hex_cells(gdf: gpd.GeoDataFrame, crs: str, *, radius_km: float = 66.0) -> pd.DataFrame:
    """Assign every outlet to one fixed-grid cell, retaining its original index.

    The projected grid has origin (0, 0) and a pointy-top circumradius in km.
    Cube-coordinate rounding assigns boundary ties deterministically: round halves
    upward, then repair the largest rounding error in q, r, s priority order.
    Input geometry must consist of finite, nonempty points with a declared CRS.
    """
    target = CRS.from_user_input(crs)
    if not target.is_projected or any(a.unit_conversion_factor != 1.0 for a in target.axis_info):
        raise ValueError("Hex-grid CRS must be projected with metre axes")
    if not np.isfinite(radius_km) or radius_km <= 0:
        raise ValueError("Hex radius must be finite and positive")
    if gdf.crs is None or gdf.empty:
        raise ValueError("Outlet points need a CRS and at least one row")
    if gdf.index.hasnans or (gdf.index.astype(str).str.strip() == "").any():
        raise ValueError("Outlet identifiers must be nonmissing and nonempty")
    if not gdf.index.astype(str).is_unique:
        raise ValueError("Outlet identifiers must be unique when represented as strings")
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any() or not gdf.geom_type.eq("Point").all():
        raise ValueError("Every outlet must have a nonempty Point geometry")
    points = gdf.to_crs(target)
    xy = np.column_stack([points.geometry.x, points.geometry.y])
    if not np.isfinite(xy).all():
        raise ValueError("Every outlet must have finite projected coordinates")
    radius = radius_km * 1000.0
    q = (np.sqrt(3) * xy[:, 0] / 3 - xy[:, 1] / 3) / radius
    r = 2 * xy[:, 1] / (3 * radius)
    cube = np.column_stack([q, r, -q - r])
    rounded = np.floor(cube + 0.5).astype(np.int64)
    repair = np.abs(rounded - cube).argmax(axis=1)
    rows = np.arange(len(points))
    rounded[rows, repair] -= rounded.sum(axis=1)
    return pd.DataFrame(
        {"hex_id": [f"{q}:{r}" for q, r in rounded[:, :2]], "q": rounded[:, 0], "r": rounded[:, 1]},
        index=gdf.index.copy(),
    )


def aggregate_hex(
    gdf: gpd.GeoDataFrame,
    value_col: str,
    crs: str,
    *,
    categories: list[str] | None = None,
    radius_km: float = 66.0,
) -> gpd.GeoDataFrame:
    """Summarize occupied cells by finite-value median or declared categorical mode.

    All-missing occupied cells remain in the output with a missing value. Category
    mode ties select the first category in the supplied order; unknown labels fail.
    Counts always refer to individual outlets, without area weighting.
    """
    membership = assign_hex_cells(gdf, crs, radius_km=radius_km)
    values = pd.Series(gdf[value_col])
    if categories is None:
        values = pd.to_numeric(values, errors="raise").astype(float)
        values = values.where(np.isfinite(values))
    else:
        if not categories or not pd.Index(categories).is_unique or pd.isna(categories).any():
            raise ValueError("Categories must be a nonempty unique ordered list without missing labels")
        if not values.dropna().isin(categories).all():
            raise ValueError("Every nonmissing category must occur in the declared category order")
    records = membership.assign(value=values.to_numpy())
    grouped = records.groupby("hex_id", sort=True)
    summary = pd.DataFrame(grouped.agg(n_total=("value", "size"), n_valid=("value", "count")))
    summary["n_missing"] = summary.n_total - summary.n_valid
    if categories is None:
        summary["value"] = grouped.value.median()
    else:
        frequencies = pd.crosstab(records.hex_id, records.value).reindex(
            columns=categories, fill_value=0
        )
        summary["value"] = frequencies.idxmax(axis=1).reindex(summary.index)
        summary["n_categories"] = grouped.value.nunique()
    axial = grouped[["q", "r"]].first().reindex(summary.index)
    radius = radius_km * 1000.0
    centres = np.column_stack(
        [
            np.sqrt(3) * radius * (axial.q + axial.r / 2),
            1.5 * radius * axial.r,
        ]
    )
    angles = np.deg2rad([30, 90, 150, 210, 270, 330])
    offsets = radius * np.column_stack([np.cos(angles), np.sin(angles)])
    geometry = [Polygon(centre + offsets) for centre in centres]
    return gpd.GeoDataFrame(summary.reset_index(), geometry=geometry, crs=crs)


def export_hex_support(
    gdf: gpd.GeoDataFrame,
    value_col: str,
    cells: gpd.GeoDataFrame,
    crs: str,
    path: str | Path,
    *,
    categories: list[str] | None = None,
    radius_km: float = 66.0,
) -> None:
    """Write versionable grid, reducer, cell-support and outlet-membership provenance."""
    membership = assign_hex_cells(gdf, crs, radius_km=radius_km)
    report = {
        "value_column": value_col,
        "grid": {
            "crs": CRS.from_user_input(crs).to_wkt(),
            "orientation": "pointy-top",
            "circumradius_km": radius_km,
            "origin_m": [0.0, 0.0],
            "boundary_assignment": "cube rounding; half upward; repair priority q,r,s",
        },
        "reducer": "finite-value median" if categories is None else "category mode",
        "category_tie_order": categories,
        "support": "gauge outlet locations; no area weighting; empty cells omitted",
        "cells": json.loads(
            cells.drop(columns="geometry").to_json(orient="records", double_precision=15)
        ),
        "gauge_membership": {str(gauge): cell for gauge, cell in membership.hex_id.items()},
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
