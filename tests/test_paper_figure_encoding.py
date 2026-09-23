"""Run with pixi run --as-is python tests/test_paper_figure_encoding.py."""

from pathlib import Path
import sys

from matplotlib.colors import BoundaryNorm
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.generate_budyko_figure import _off_axis_counts
from scripts.plot_coldregion_gradient import binned_median
from src.plots.paper_maps import _class_counts, _format_edge_labels


def main():
    edges = np.array([0.0, 1.0, 2.0, 4.0])
    values = np.array([-10.0, 0.0, 1.0, 2.0, 4.0, 10.0, np.nan, np.inf, -np.inf])
    counts = _class_counts(values, edges)
    np.testing.assert_array_equal(counts, [2, 1, 3])
    membership = BoundaryNorm(edges, 3, clip=True)(values[np.isfinite(values)])
    np.testing.assert_array_equal(counts, np.bincount(membership, minlength=3))
    np.testing.assert_array_equal(_class_counts(np.array([]), edges), [0, 0, 0])
    np.testing.assert_array_equal(_class_counts(np.array([np.nan]), edges), [0, 0, 0])
    assert _format_edge_labels(edges) == ["−∞", "1", "2", "+∞"]
    bins = binned_median(
        pd.Series([0.0, 5.0, 100.00000000000004, np.nan, 7.0, np.inf]),
        pd.Series([1.0, np.nan, 3.0, 8.0, np.inf, 2.0]),
        [0, 5, 10, 100],
    )
    np.testing.assert_array_equal(bins["n"], [1, 0, 1])
    np.testing.assert_allclose(bins["median"], [1, np.nan, 3], equal_nan=True)
    empty = binned_median(pd.Series([], dtype=float), pd.Series([], dtype=float), [0, 5, 10])
    np.testing.assert_array_equal(empty["n"], [0, 0])
    outside = _off_axis_counts(
        pd.DataFrame({"aridity_index": [0, 4, 4, 1], "evaporative_index": [0, -1, 2, 0]})
    )
    assert outside == {"x_below": 0, "x_above": 2, "y_below": 1, "y_above": 1, "outside_union": 2}
    print("Paper figure encoding checks passed")


if __name__ == "__main__":
    main()
