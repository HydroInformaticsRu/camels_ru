"""Detect nested catchments in the CAMELS-RU dataset.

For each gauge, identifies which other watershed polygons contain it
(point-in-polygon), then computes nesting statistics.

Uses a spatial join for efficiency rather than O(n^2) loops.
Only considers parent-child relationships where the parent watershed
is strictly larger than the child, which ensures the containment
graph is a DAG (no cycles from overlapping same-size catchments).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

_PROJECT_ROOT = Path(__file__).parent.parent
_DATA_DIR = _PROJECT_ROOT / "data" / "CAMELS_RU"

WATERSHEDS_PATH = _DATA_DIR / "geometry_v2" / "camels_ru_watersheds.gpkg"
GAUGES_PATH = _DATA_DIR / "geometry_v2" / "camels_ru_gauges.gpkg"


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    print("Loading watersheds...")
    watersheds = gpd.read_file(WATERSHEDS_PATH)
    print(f"  {len(watersheds)} watersheds loaded (CRS: {watersheds.crs})")

    print("Loading gauges...")
    gauges = gpd.read_file(GAUGES_PATH)
    print(f"  {len(gauges)} gauges loaded (CRS: {gauges.crs})")

    # Ensure both are in EPSG:4326
    if watersheds.crs is None or watersheds.crs.to_epsg() != 4326:
        watersheds = watersheds.to_crs(epsg=4326)
    if gauges.crs is None or gauges.crs.to_epsg() != 4326:
        gauges = gauges.to_crs(epsg=4326)

    # ------------------------------------------------------------------
    # 2. Spatial join: which watershed polygons contain each gauge point?
    # ------------------------------------------------------------------
    print("\nRunning spatial join (point-in-polygon)...")
    gauges_slim = gauges[["gauge_id", "geometry"]].rename(columns={"gauge_id": "child_gauge_id"})
    watersheds_slim = watersheds[["gauge_id", "area_km2", "geometry"]].rename(
        columns={"gauge_id": "parent_gauge_id", "area_km2": "parent_area_km2"}
    )

    joined = gpd.sjoin(
        gauges_slim,
        watersheds_slim,
        how="inner",
        predicate="within",
    )

    # ------------------------------------------------------------------
    # 3. Remove self-matches and add child area
    # ------------------------------------------------------------------
    joined = joined[joined["child_gauge_id"] != joined["parent_gauge_id"]].copy()
    print(f"  {len(joined)} nesting pairs (excluding self-matches)")

    area_lookup = watersheds.set_index("gauge_id")["area_km2"].to_dict()
    joined["child_area_km2"] = joined["child_gauge_id"].map(area_lookup)

    # ------------------------------------------------------------------
    # 4. Keep only pairs where parent area > child area
    #    This eliminates cycles from overlapping similar-size catchments
    # ------------------------------------------------------------------
    joined = joined[joined["parent_area_km2"] > joined["child_area_km2"]].copy()
    print(f"  {len(joined)} valid nesting pairs (parent area > child area)")

    # ------------------------------------------------------------------
    # 5. Compute statistics
    # ------------------------------------------------------------------
    total_gauges = len(gauges)
    nested_gauges = joined["child_gauge_id"].nunique()
    pct_nested = 100.0 * nested_gauges / total_gauges

    # Build DAG: child -> set of parents (only strictly larger parents)
    parents_per_child: dict = joined.groupby("child_gauge_id")["parent_gauge_id"].apply(set).to_dict()

    all_gauge_ids = set(gauges["gauge_id"])

    # Also build children_of: parent -> set of children (for topological sort)
    children_of: dict = {}
    for child, parents in parents_per_child.items():
        for p in parents:
            children_of.setdefault(p, set()).add(child)

    # Compute depth iteratively using BFS from roots (nodes with no parents)
    # depth(node) = 0 if no parents, else 1 + max(depth of parents)
    # We process in topological order: largest areas first (they have depth 0),
    # then propagate downward.
    depth: dict = dict.fromkeys(all_gauge_ids, 0)

    # Sort all gauges by area descending — largest first
    gauges_by_area = sorted(all_gauge_ids, key=lambda g: area_lookup.get(g, 0), reverse=True)

    for g in gauges_by_area:
        parents = parents_per_child.get(g, set())
        if parents:
            depth[g] = 1 + max(depth.get(p, 0) for p in parents)

    max_depth = max(depth.values()) if depth else 0
    deepest_gauge = max(depth, key=depth.get)  # type: ignore[arg-type]

    # Distribution of nesting counts
    nesting_counts = joined.groupby("child_gauge_id").size()

    # ------------------------------------------------------------------
    # 6. Print results
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("NESTED CATCHMENT STATISTICS -- CAMELS-RU")
    print("=" * 65)
    print(f"Total gauges checked:          {total_gauges}")
    print(f"Gauges nested in >= 1 other:   {nested_gauges}")
    print(f"Percentage nested:             {pct_nested:.1f}%")
    print(f"Total nesting pairs:           {len(joined)}")
    print(f"Maximum nesting depth:         {max_depth}")
    print(f"  (deepest gauge: {deepest_gauge}, depth={depth[deepest_gauge]})")
    print()

    # Distribution of direct-parent counts
    print("Distribution of parent counts per nested gauge:")
    dist = nesting_counts.value_counts().sort_index()
    for n_parents, count in dist.items():
        print(f"  {n_parents:3d} parent(s): {count:5d} gauges")
    print()

    # Example nested pairs (sorted by child area, smallest first)
    print("Example nested pairs (10 smallest children by area):")
    examples = (
        joined[["child_gauge_id", "parent_gauge_id", "child_area_km2", "parent_area_km2"]]
        .sort_values("child_area_km2")
        .head(10)
    )
    print(
        examples.to_string(
            index=False,
            float_format=lambda x: f"{x:,.1f}",
        )
    )
    print()

    # Show the deepest nesting chain
    print(f"Deepest nesting chain (gauge {deepest_gauge}, depth={max_depth}):")
    current = deepest_gauge
    chain = [current]
    visited = {current}
    while True:
        parents = parents_per_child.get(current, set())
        if not parents:
            break
        # Pick the smallest parent (most immediate container)
        parents_with_area = [(p, area_lookup.get(p, float("inf"))) for p in parents if p not in visited]
        if not parents_with_area:
            break
        parents_with_area.sort(key=lambda x: x[1])
        current = parents_with_area[0][0]
        chain.append(current)
        visited.add(current)

    for i, g in enumerate(chain):
        area = area_lookup.get(g, float("nan"))
        indent = "  " * i
        arrow = "-> " if i > 0 else ""
        print(f"  {indent}{arrow}{g} (area={area:,.1f} km2)")

    # Depth distribution
    print("\nDistribution of nesting depths across all gauges:")
    depth_series = pd.Series(depth)
    depth_dist = depth_series.value_counts().sort_index()
    for d, count in depth_dist.items():
        label = "not nested" if d == 0 else f"depth {d}"
        print(f"  {label}: {count:5d} gauges")

    print("\nDone.")


if __name__ == "__main__":
    main()
