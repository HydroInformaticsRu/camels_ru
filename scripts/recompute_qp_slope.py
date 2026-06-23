"""Recompute per-gauge OLS slope of annual discharge on annual precipitation.

Sources the median-slope figures reported in
``paper/overleaf/sections/05_forcing_uncertainty.tex`` (Sect. 5.2): the per-gauge
regression of annual discharge on annual precipitation, its median across gauges,
the fraction of gauges with slope > 1, and the karst association of those gauges.

Reads the released artifacts only (no ``data/`` dependency). The hydrological year
(Oct--Sep) is labelled ``year + (month >= 10)``, matching
``scripts/recompute_forcing_numbers.py:hydro_year_sum``. A hydrological year counts
toward a gauge only if it has at least ``MIN_DAYS`` valid discharge days, so that
partial-year sums do not deflate the slope.

Usage:
    pixi run python scripts/recompute_qp_slope.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REL = Path("release/CAMELS_RU_v1.0")
MIN_DAYS = 300
MIN_YEARS = 5


def hydro_year(time: xr.DataArray) -> xr.DataArray:
    """Return the hydrological-year (Oct--Sep) label for each time step."""
    return (time.dt.year + (time.dt.month >= 10)).astype(int).rename("hydro_year")


def annual_discharge(dq: xr.DataArray, hy: xr.DataArray) -> xr.DataArray:
    """Per-gauge hydro-year discharge sum (mm), NaN if < ``MIN_DAYS`` valid days."""
    total = dq.groupby(hy).sum("time", min_count=1)
    valid = dq.notnull().groupby(hy).sum("time")
    return total.where(valid >= MIN_DAYS)


def per_gauge_slopes(
    q_ann: xr.DataArray, p_da: xr.DataArray, hy: xr.DataArray
) -> tuple[np.ndarray, np.ndarray]:
    """Return OLS slopes of annual Q on annual P and the matching gauge IDs.

    Only gauges with at least ``MIN_YEARS`` common (Q, P) hydrological years and a
    non-degenerate precipitation range contribute.
    """
    p_ann = p_da.groupby(hy).sum("time", min_count=1).transpose(*q_ann.dims)
    q_vals = q_ann.values
    p_vals = p_ann.values
    gauge_ids = q_ann["gauge_id"].values.astype(str)
    slopes: list[float] = []
    kept: list[str] = []
    for i in range(q_vals.shape[0]):
        mask = np.isfinite(q_vals[i]) & np.isfinite(p_vals[i])
        if mask.sum() >= MIN_YEARS and np.ptp(p_vals[i][mask]) > 0:
            slopes.append(float(np.polyfit(p_vals[i][mask], q_vals[i][mask], 1)[0]))
            kept.append(gauge_ids[i])
    return np.array(slopes), np.array(kept)


def main() -> None:
    """Print median slope, fraction exceeding unity, and the karst association."""
    dq = xr.open_dataset(REL / "camels_ru_discharge.nc")["discharge_mm"]
    forcing = xr.open_dataset(REL / "camels_ru_forcing.nc")
    hy = hydro_year(dq["time"])
    q_ann = annual_discharge(dq, hy)

    attrs = pd.read_csv(REL / "camels_ru_attributes.csv")
    attrs["gauge_id"] = attrs["gauge_id"].astype(str)
    karst = attrs.set_index("gauge_id")["kar_pc_use"]

    print(
        f"Per-gauge OLS slope of annual Q on annual P "
        f"(year valid if >= {MIN_DAYS} days; >= {MIN_YEARS} common years):"
    )
    for product in ("era5", "mswep", "gpcp"):
        slopes, gauge_ids = per_gauge_slopes(q_ann, forcing[f"precip_{product}"], hy)
        gt1 = slopes > 1
        karst_all = float(karst.reindex(gauge_ids).median())
        karst_gt1 = float(karst.reindex(gauge_ids[gt1]).median())
        print(
            f"  {product.upper():6s} median={np.median(slopes):.3f}  "
            f"frac>1={100 * gt1.mean():.1f}%  n={len(slopes)}  "
            f"karst%% median: all={karst_all:.2f} slope>1={karst_gt1:.2f}"
        )


if __name__ == "__main__":
    main()
