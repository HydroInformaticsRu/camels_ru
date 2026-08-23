"""Regression test: HydroATLAS area weighting must not scale attributes by catchment coverage.

Before 2026-08-23 the weights were intersection_area / catchment_area without renormalisation,
so every attribute equalled the true area-weighted mean times ``area_fraction_used``
(science-review Domain Expert CRITICAL-1).

Run: ``pixi run python tests/test_hydroatlas_weights.py``
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.static.hydro_atlas_reader import area_weighted_mean


def test_partial_coverage_does_not_scale_the_mean():
    # Two polygons cover only 60 % of the catchment; the mean must still be the area-weighted mean.
    data = np.array([[100.0, 10.0], [50.0, 30.0]])
    inter_areas = np.array([0.4, 0.2])  # catchment area 1.0, coverage 0.6
    out = area_weighted_mean(data, inter_areas)
    np.testing.assert_allclose(out, [(100 * 0.4 + 50 * 0.2) / 0.6, (10 * 0.4 + 30 * 0.2) / 0.6])


def test_nan_polygon_is_dropped_per_variable():
    data = np.array([[100.0, np.nan], [50.0, 30.0]])
    inter_areas = np.array([0.4, 0.2])
    out = area_weighted_mean(data, inter_areas)
    np.testing.assert_allclose(out, [(100 * 0.4 + 50 * 0.2) / 0.6, 30.0])


def test_all_nan_variable_stays_nan():
    data = np.array([[np.nan], [np.nan]])
    assert np.isnan(area_weighted_mean(data, np.array([1.0, 1.0]))[0])


if __name__ == "__main__":
    test_partial_coverage_does_not_scale_the_mean()
    test_nan_polygon_is_dropped_per_variable()
    test_all_nan_variable_stays_nan()
    print("PASS: test_hydroatlas_weights")
