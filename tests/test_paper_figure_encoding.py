"""Run with pixi run --as-is python tests/test_paper_figure_encoding.py."""

from pathlib import Path
import sys

import geopandas as gpd
from matplotlib.colors import BoundaryNorm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.generate_budyko_figure import _off_axis_counts
from scripts.plot_coldregion_gradient import binned_median
from src.plots.paper_maps import _class_counts, _format_edge_labels, continuous_multiplot


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
    # A reserved legend row must not cover the map; bar counts retain clipped bins.
    points = gpd.GeoDataFrame(
        {"value": [-1.0, 0.5, 2.0, np.nan]},
        geometry=gpd.points_from_xy([40, 70, 100, 130], [50, 55, 60, 65]),
        crs="EPSG:4326",
    )
    fig = continuous_multiplot(
        points,
        ["value"],
        ncols=1,
        panel_size=(6.3, 3.9),
        bin_intervals={"value": [0, 1, 2]},
    )
    fig.canvas.draw()
    map_ax, count_ax, hist_ax, cb_ax = fig.axes
    assert not any("Finite n=" in text.get_text() for text in map_ax.texts)
    assert count_ax.texts[0].get_text() == "Finite n=3; missing n=1 (grey)"
    assert count_ax.get_position().y1 < map_ax.get_position().y0
    assert hist_ax.get_position().y1 < count_ax.get_position().y0
    assert cb_ax.get_position().y1 < hist_ax.get_position().y0
    np.testing.assert_array_equal([bar.get_height() for bar in hist_ax.patches], [2, 1])
    plt.close(fig)
    print("Paper figure encoding checks passed")


if __name__ == "__main__":
    main()
