"""Regression test: gap fills must bridge observations, never extrapolate into long gaps.

``interpolate(limit=6)`` filled the first six days of every gap (89 % of the 15 863
released fill days abutted a longer gap; 2026-08 review, Domain Expert M-3).
``_edge_fills`` reverts such runs at packaging time and ``fill_short_gaps`` stops
the parser from producing them.

Run: ``pixi run python tests/test_gap_fill_edges.py``
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_processing.ais import fill_short_gaps  # noqa: E402
from scripts.package_dataset import _edge_fills  # noqa: E402


def test_edge_fills_keep_bridges_and_drop_extrapolations():
    #            obs  fill fill obs | obs fill fill miss miss | fill obs
    present = np.array([[1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1]], dtype=bool)
    filled = np.array([[0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 0]], dtype=bool)
    edge = _edge_fills(present, filled)
    assert edge.tolist() == [[0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0]]


def test_edge_fills_at_grid_boundary_are_dropped():
    present = np.array([[1, 1, 1]], dtype=bool)
    filled = np.array([[1, 0, 1]], dtype=bool)
    assert _edge_fills(present, filled).tolist() == [[1, 0, 1]]


def test_fill_short_gaps_only_fills_runs_of_at_most_six_days():
    idx = pd.date_range("2020-01-01", periods=20, freq="D")
    s = pd.Series(np.arange(20, dtype=float), index=idx)
    s.iloc[2:5] = np.nan  # 3-day gap -> filled
    s.iloc[8:16] = np.nan  # 8-day gap -> left missing entirely
    out = fill_short_gaps(s)
    assert out.iloc[2:5].notna().all()
    assert out.iloc[8:16].isna().all()
    assert out.iloc[16:].notna().all()


if __name__ == "__main__":
    test_edge_fills_keep_bridges_and_drop_extrapolations()
    test_edge_fills_at_grid_boundary_are_dropped()
    test_fill_short_gaps_only_fills_runs_of_at_most_six_days()
    print("PASS: test_gap_fill_edges")
