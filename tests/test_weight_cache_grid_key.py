"""Regression test: watershed weight cache must be grid-keyed.

Reproduces the 2023 ERA5-Land "temperature gap" silent failure
(2026-06-23 triad investigation): ``_get_or_compute_weights`` returned a
*stale* cached fractional-weight file whose ``lat``/``lon`` coordinates no
longer matched the current ``ds_extent`` grid (ERA5-Land tiles had widened
from 1511 to 1601 lon columns). xarray then broadcast-aligned the mismatched
weights against ``ds_extent.where(weights > 0)`` -> all-NaN -> climatology fill.

The cache is keyed by ``{gauge_id}/{grid_resolution}`` only, NOT by grid shape,
so the stale value "hit" the cache. A hardened helper must validate the cached
coordinates against the live grid and recompute on mismatch.

Run: ``pixi run python tests/test_weight_cache_grid_key.py``
Exits 0 on success, non-zero on regression.
"""

from pathlib import Path
import sys
import tempfile

import numpy as np
from shapely.geometry import box
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))
from src.meteo.aggregation import _get_or_compute_weights  # noqa: E402

GRID_RES = 0.10
GAUGE_ID = "test_gauge"


def _make_extent(lats: np.ndarray, lons: np.ndarray) -> xr.Dataset:
    """A minimal ds_extent carrying only lat/lon coords (shape is what matters)."""
    data = np.zeros((len(lats), len(lons)), dtype=np.float32)
    return xr.Dataset(
        {"t_mean": (("lat", "lon"), data)},
        coords={"lat": lats, "lon": lons},
    )


def test_stale_cache_grid_is_recomputed() -> None:
    """A cached weight grid that differs from ds_extent must be recomputed."""
    # Sub-cell watershed so it routes through the small-watershed weighted path.
    geom = box(50.00, 50.00, 50.04, 50.04)

    narrow_lats = np.array([49.9, 50.0, 50.1])
    narrow_lons = np.array([49.9, 50.0, 50.1])
    # Wider grid: one extra lon column, exactly the failure mode (tiles widened).
    wide_lats = np.array([49.9, 50.0, 50.1])
    wide_lons = np.array([49.9, 50.0, 50.1, 50.2])

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)

        # 1. Prime the cache against the NARROW grid (simulates 2008-first bulk run).
        first = _get_or_compute_weights(
            cache_dir, GAUGE_ID, GRID_RES, geom, _make_extent(narrow_lats, narrow_lons)
        )
        assert first.sizes["lon"] == 3, "priming run should match the narrow grid"

        # 2. Re-request weights for the SAME gauge but a WIDER grid (2023 tiles).
        #    Buggy code returns the stale 3-col cache; hardened code recomputes.
        wide_extent = _make_extent(wide_lats, wide_lons)
        second = _get_or_compute_weights(cache_dir, GAUGE_ID, GRID_RES, geom, wide_extent)

    assert second.sizes["lon"] == wide_extent.sizes["lon"], (
        f"stale cache leaked: weights have {second.sizes['lon']} lon cells, "
        f"current grid has {wide_extent.sizes['lon']}"
    )
    assert np.array_equal(second.lon.values, wide_lons), (
        "recomputed weights must carry the current grid's lon coordinates"
    )
    assert np.array_equal(second.lat.values, wide_lats), (
        "recomputed weights must carry the current grid's lat coordinates"
    )


if __name__ == "__main__":
    test_stale_cache_grid_is_recomputed()
    print("PASS: test_weight_cache_grid_key")
