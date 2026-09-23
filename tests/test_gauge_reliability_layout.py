"""Keep point-map legends inside the rendered geographic frame at export DPI."""

from pathlib import Path
import sys
from unittest.mock import patch

import geopandas as gpd
from matplotlib.collections import PathCollection
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import plot_gauge_reliability as plot


def main():
    gauge = gpd.GeoDataFrame(
        {
            "grade": ["A", "A", "B", "C", "D", "F", "ungraded"],
            "pct_a": [100.0, 100.0, 85.0, 60.0, 30.0, 0.0, np.nan],
        },
        geometry=gpd.points_from_xy([30, 40, 60, 80, 100, 130, 170], [60, 55, 65, 60, 55, 65, 60]),
        crs="EPSG:4326",
    )

    def basemap(ax, points, _projection):
        ax.axis("off")
        plot._set_extent_from_data(ax, points)

    with patch.object(plot, "_basemap", basemap):
        fig = plot.build_figure(gauge)
    axes = {ax.get_label(): ax for ax in fig.axes}
    grade = axes["map_grade"]
    reliability = axes["map_reliability"]
    assert sum(len(c.get_offsets()) for c in grade.collections if isinstance(c, PathCollection)) == 7
    assert (
        sum(len(c.get_offsets()) for c in reliability.collections if isinstance(c, PathCollection)) == 7
    )
    np.testing.assert_array_equal(reliability.collections[-1].get_array(), [100, 100, 85, 60, 30, 0])
    for dpi in (150, 300):
        fig.set_dpi(dpi)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for parent, rows in (
            (grade, ["grade_legend"]),
            (reliability, ["reliability_counts", "reliability_scale"]),
        ):
            frame = parent.get_window_extent(renderer)
            for name in rows:
                row = axes[name]
                row_frame = row.get_window_extent(renderer)
                np.testing.assert_allclose([row_frame.x0, row_frame.x1], [frame.x0, frame.x1], atol=0.1)
                content = row.get_tightbbox(renderer)
                assert content.x0 >= frame.x0 - 0.1, (name, content, frame)
                assert content.x1 <= frame.x1 + 0.1, (name, content, frame)
                assert content.y1 < frame.y0, (name, content, frame)
        legend = axes["grade_legend"].get_legend().get_window_extent(renderer)
        assert legend.y0 > reliability._left_title.get_window_extent(renderer).y1
        for row in (axes["grade_legend"], axes["reliability_counts"], axes["reliability_scale"]):
            assert row.get_tightbbox(renderer).y0 >= 0
    plt.close(fig)
    print("Gauge point counts and rendered-frame legend alignment passed at 150/300 dpi")


if __name__ == "__main__":
    main()
