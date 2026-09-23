"""Run with pixi run --as-is python tests/test_hex_maps.py."""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from plots.hex_maps import aggregate_hex, assign_hex_cells, export_hex_support


def rejected(call):
    """Require explicit invalid-input failure."""
    try:
        call()
    except (ValueError, TypeError):
        return
    raise AssertionError("Invalid input was accepted")


def main():
    """Check fixed-grid support and aggregation, including boundaries and missingness."""
    radius = 66_000.0
    points = gpd.GeoDataFrame(
        {"v": [1.0, 3.0, np.nan, 20.0, np.inf], "grade": ["A", "F", None, "A", None]},
        index=pd.Index(["a", "b", "c", "d", "e"], name="gauge_id"),
        geometry=[Point(0, 0), Point(1, 1), Point(-1, -1), Point(4 * radius, 0), Point(0, 4 * radius)],
        crs="EPSG:3857",
    )
    before = points.copy(deep=True)
    cells = assign_hex_cells(points, "EPSG:3857")
    assert cells.index.equals(points.index) and cells.hex_id.notna().all()
    assert len(cells) == len(points)
    assert cells.loc["a", "hex_id"] == "0:0"
    pd.testing.assert_frame_equal(
        assign_hex_cells(points.loc[["d", "a"]], "EPSG:3857"), cells.loc[["d", "a"]]
    )
    # Exact shared edge / vertex: fixed rounding assigns one covering cell, repeatably.
    boundary = gpd.GeoDataFrame(
        {"v": [2.0, 4.0]},
        geometry=[Point(np.sqrt(3) * radius / 2, 0), Point(0, radius)],
        crs="EPSG:3857",
    )
    assigned = assign_hex_cells(boundary, "EPSG:3857")
    pd.testing.assert_frame_equal(
        assigned, assign_hex_cells(boundary.iloc[::-1], "EPSG:3857").sort_index()
    )
    boundary_cells = aggregate_hex(boundary, "v", "EPSG:3857").set_index("hex_id")
    assert boundary_cells.n_total.sum() == 2
    for i, row in assigned.iterrows():
        assert boundary_cells.loc[row.hex_id].geometry.buffer(1e-7).covers(boundary.geometry.loc[i])
    aggregate = aggregate_hex(points, "v", "EPSG:3857").set_index("hex_id")
    assert (
        aggregate.n_total.sum() == 5 and aggregate.n_valid.sum() == 3 and aggregate.n_missing.sum() == 2
    )
    origin = aggregate.loc["0:0"]
    assert origin.value == 2.0 and origin.n_total == 3 and origin.n_missing == 1
    assert pd.isna(aggregate.loc[cells.loc["e", "hex_id"], "value"])
    mode = aggregate_hex(points, "grade", "EPSG:3857", categories=["F", "A"]).set_index("hex_id")
    assert mode.loc["0:0", "value"] == "F" and mode.loc["0:0", "n_categories"] == 2
    pd.testing.assert_frame_equal(points, before)
    rejected(lambda: assign_hex_cells(points.set_crs(None, allow_override=True), "EPSG:3857"))
    rejected(lambda: assign_hex_cells(points, "EPSG:4326"))
    rejected(lambda: assign_hex_cells(points.iloc[:0], "EPSG:3857"))
    rejected(lambda: assign_hex_cells(points, "EPSG:3857", radius_km=0))
    rejected(lambda: aggregate_hex(points, "grade", "EPSG:3857", categories=["A"]))
    rejected(lambda: aggregate_hex(points, "grade", "EPSG:3857", categories=["A", "A"]))
    for bad in [Point(), Point(np.nan, 0), LineString([(0, 0), (1, 1)])]:
        invalid = points.copy()
        invalid.loc["a", "geometry"] = bad
        rejected(lambda invalid=invalid: assign_hex_cells(invalid, "EPSG:3857"))
    rejected(lambda: assign_hex_cells(pd.concat([points, points]), "EPSG:3857"))
    for bad_id in [None, "", "  "]:
        bad_ids = points.copy()
        bad_ids.index = [bad_id, "b", "c", "d", "e"]
        rejected(lambda bad_ids=bad_ids: assign_hex_cells(bad_ids, "EPSG:3857"))
    missing = points.copy()
    missing["grade"] = None
    assert aggregate_hex(missing, "grade", "EPSG:3857", categories=["A", "F"]).value.isna().all()
    destination = Path(__file__).resolve().parents[1] / ".tmp/hex_revision_2026-09-23/test_support.json"
    export_hex_support(points, "v", aggregate.reset_index(), "EPSG:3857", destination)
    report = json.loads(destination.read_text())
    assert report["gauge_membership"] == cells.hex_id.to_dict()
    assert sum(cell["n_total"] for cell in report["cells"]) == 5
    assert report["grid"]["origin_m"] == [0, 0]
    assert any(c["value"] is None for c in report["cells"])
    missing_cells = aggregate_hex(missing, "grade", "EPSG:3857", categories=["A", "F"])
    export_hex_support(missing, "grade", missing_cells, "EPSG:3857", destination, categories=["A", "F"])
    assert all(c["value"] is None for c in json.loads(destination.read_text())["cells"])
    print("Hex membership, support, median, mode, boundary and validation checks passed")


if __name__ == "__main__":
    main()
