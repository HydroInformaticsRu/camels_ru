#!/usr/bin/env python3
"""Validate CAMELS-RU discharge against GRDC where temporal overlap exists.

Parses GRDC daily discharge files (DOS-ASCII with ';' delimiter), matches
to CAMELS-RU gauges by spatial proximity (<25 km) and catchment area ratio
(0.5–2.0), then computes comparison statistics for overlapping periods.

Usage:
    python scripts/validate_grdc.py [--grdc-dir PATH] [--max-dist 25] [--output-dir PATH]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

gpd.options.io_engine = "pyogrio"

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
COMPOUND_DIR = DATA_DIR / "HydroData" / "Compound"
GEOM_DIR = DATA_DIR / "geometry"

GRDC_DEFAULT = Path("/media/dmbrmv/ssd_2tb/CAMELS_RU/HydroData/GRDC")

PERIOD_START = "2008-01-01"
PERIOD_END = "2023-12-31"


@dataclass
class GRDCStation:
    """Parsed GRDC station metadata + time series."""

    grdc_no: str
    river: str
    station: str
    country: str
    lat: float
    lon: float
    area_km2: float | None
    time_series_range: str
    discharge: pd.Series  # daily Q in m³/s, datetime index
    file_path: str


def parse_grdc_file(path: Path) -> GRDCStation | None:
    """Parse a single GRDC daily discharge file.

    Handles Windows line endings and the GRDC header format.

    Args:
        path: Path to *_Q_Day.Cmd.txt file.

    Returns:
        GRDCStation or None if parsing fails or file has no data.
    """
    meta: dict[str, str] = {}
    data_rows: list[tuple[str, float]] = []

    with open(path, encoding="latin-1") as fh:
        in_data = False
        for raw_line in fh:
            line = raw_line.strip().rstrip("\r")
            if not in_data:
                if line.startswith("# GRDC-No.:"):
                    meta["grdc_no"] = line.split(":", 1)[1].strip()
                elif line.startswith("# River:"):
                    meta["river"] = line.split(":", 1)[1].strip()
                elif line.startswith("# Station:"):
                    meta["station"] = line.split(":", 1)[1].strip()
                elif line.startswith("# Country:"):
                    meta["country"] = line.split(":", 1)[1].strip()
                elif line.startswith("# Latitude"):
                    try:
                        meta["lat"] = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        return None
                elif line.startswith("# Longitude"):
                    try:
                        meta["lon"] = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        return None
                elif line.startswith("# Catchment area"):
                    try:
                        val = float(line.split(":", 1)[1].strip())
                        meta["area_km2"] = val if val > 0 else None
                    except ValueError:
                        meta["area_km2"] = None
                elif line.startswith("# Time series:"):
                    meta["time_series_range"] = line.split(":", 1)[1].strip()
                elif line.startswith("YYYY-MM-DD"):
                    in_data = True
            else:
                parts = line.split(";")
                if len(parts) >= 3:
                    date_str = parts[0].strip()
                    try:
                        val = float(parts[2].strip())
                        if val != -999.0:
                            data_rows.append((date_str, val))
                    except ValueError:
                        continue

    if not data_rows or "grdc_no" not in meta:
        return None

    dates, values = zip(*data_rows)
    discharge = pd.Series(
        values,
        index=pd.to_datetime(dates),
        name="q_cms",
        dtype=np.float64,
    )

    return GRDCStation(
        grdc_no=meta.get("grdc_no", ""),
        river=meta.get("river", ""),
        station=meta.get("station", ""),
        country=meta.get("country", ""),
        lat=float(meta.get("lat", 0)),
        lon=float(meta.get("lon", 0)),
        area_km2=meta.get("area_km2"),
        time_series_range=meta.get("time_series_range", ""),
        discharge=discharge,
        file_path=str(path),
    )


def load_grdc_stations(grdc_dir: Path, country: str = "RU") -> list[GRDCStation]:
    """Load all GRDC stations for a country with data overlapping 2008+.

    Args:
        grdc_dir: Root GRDC directory containing subdirectories with .txt files.
        country: ISO country code to filter.

    Returns:
        List of parsed GRDC stations with 2008+ data.
    """
    all_files = sorted(grdc_dir.rglob("*_Q_Day.Cmd.txt"))
    print(f"Found {len(all_files)} GRDC files")

    stations = []
    for f in all_files:
        st = parse_grdc_file(f)
        if st is None:
            continue
        if st.country != country:
            continue
        # Filter to stations with data in our study period
        if st.discharge.index.max() < pd.Timestamp(PERIOD_START):
            continue
        stations.append(st)

    print(f"Loaded {len(stations)} {country} stations with 2008+ data")
    return stations


def match_grdc_to_camels(
    grdc_stations: list[GRDCStation],
    camels_gauges: gpd.GeoDataFrame,
    camels_watersheds: gpd.GeoDataFrame,
    max_dist_km: float = 25.0,
    area_ratio_range: tuple[float, float] = (0.5, 2.0),
) -> list[dict]:
    """Match GRDC stations to nearest CAMELS-RU gauge.

    Uses KD-tree for fast spatial lookup, then validates with area ratio.

    Args:
        grdc_stations: Parsed GRDC stations.
        camels_gauges: CAMELS-RU gauge GeoDataFrame with point geometry.
        camels_watersheds: CAMELS-RU watershed GeoDataFrame with area_km2.
        max_dist_km: Maximum matching distance in km.
        area_ratio_range: Acceptable (min, max) area ratio for match.

    Returns:
        List of match dictionaries with metadata and distance.
    """
    # Build KD-tree from CAMELS-RU gauge coordinates
    camels_coords = np.array([(g.y, g.x) for g in camels_gauges.geometry])
    camels_ids = camels_gauges.index.tolist()

    # Get CAMELS areas from watersheds
    camels_areas = {}
    for gid in camels_ids:
        if gid in camels_watersheds.index and "area_km2" in camels_watersheds.columns:
            camels_areas[gid] = camels_watersheds.loc[gid, "area_km2"]

    tree = cKDTree(camels_coords)

    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance in km between two points."""
        R = 6371.0
        dlat = np.radians(lat2 - lat1)
        dlon = np.radians(lon2 - lon1)
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
        )
        return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    matches = []
    for st in grdc_stations:
        # Query nearest neighbor using KD-tree (degree-space), then compute true distance
        _, idx = tree.query([st.lat, st.lon])
        camels_id = camels_ids[idx]
        camels_pt = camels_gauges.geometry.iloc[idx]
        dist_km = haversine_km(st.lat, st.lon, camels_pt.y, camels_pt.x)

        if dist_km > max_dist_km:
            continue

        # Area ratio check
        camels_area = camels_areas.get(camels_id)
        grdc_area = st.area_km2
        if camels_area and grdc_area and grdc_area > 0:
            area_ratio = camels_area / grdc_area
            if not (area_ratio_range[0] <= area_ratio <= area_ratio_range[1]):
                continue
        else:
            area_ratio = None

        matches.append(
            {
                "grdc_no": st.grdc_no,
                "grdc_station": st.station,
                "grdc_river": st.river,
                "grdc_area_km2": grdc_area,
                "camels_id": camels_id,
                "camels_area_km2": camels_area,
                "distance_km": round(dist_km, 1),
                "area_ratio": round(area_ratio, 3) if area_ratio else None,
                "grdc_discharge": st.discharge,
            }
        )

    print(
        f"Matched {len(matches)} GRDC–CAMELS pairs (max {max_dist_km} km, area ratio {area_ratio_range})"
    )
    return matches


def compare_discharge(
    grdc_q: pd.Series,
    camels_q: pd.Series,
) -> dict:
    """Compare two discharge time series on their overlapping period.

    Args:
        grdc_q: GRDC daily discharge (m³/s).
        camels_q: CAMELS-RU daily discharge (m³/s).

    Returns:
        Dictionary with comparison statistics.
    """
    # Align to common dates
    common = grdc_q.index.intersection(camels_q.index)
    if len(common) < 30:
        return {"overlap_days": len(common), "r": np.nan, "nse": np.nan, "pbias": np.nan, "rmse": np.nan}

    g = grdc_q.loc[common].dropna()
    c = camels_q.loc[common].dropna()
    common2 = g.index.intersection(c.index)
    g = g.loc[common2]
    c = c.loc[common2]

    if len(g) < 30:
        return {"overlap_days": len(g), "r": np.nan, "nse": np.nan, "pbias": np.nan, "rmse": np.nan}

    # Pearson r
    r = np.corrcoef(g.values, c.values)[0, 1]

    # NSE (GRDC as "observed", CAMELS as "simulated" — arbitrary choice)
    ss_res = np.sum((c.values - g.values) ** 2)
    ss_tot = np.sum((g.values - g.mean()) ** 2)
    nse = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    # PBIAS (%)
    pbias = 100 * (c.values - g.values).sum() / g.values.sum() if g.values.sum() > 0 else np.nan

    # RMSE
    rmse = np.sqrt(np.mean((c.values - g.values) ** 2))

    return {
        "overlap_days": len(g),
        "overlap_start": str(g.index.min().date()),
        "overlap_end": str(g.index.max().date()),
        "r": round(r, 4),
        "nse": round(nse, 4),
        "pbias": round(pbias, 1),
        "rmse": round(rmse, 2),
        "grdc_mean_cms": round(g.mean(), 1),
        "camels_mean_cms": round(c.mean(), 1),
    }


def main() -> None:
    """Run GRDC validation."""
    parser = argparse.ArgumentParser(description="Validate CAMELS-RU against GRDC")
    parser.add_argument("--grdc-dir", type=Path, default=GRDC_DEFAULT)
    parser.add_argument("--max-dist", type=float, default=25.0, help="Max matching distance (km)")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load CAMELS-RU
    print("Loading CAMELS-RU gauges and watersheds...")
    gauges = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
    gauges.set_index("gauge_id", inplace=True)
    gauges.index = gauges.index.astype(str)

    watersheds = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    watersheds.set_index("gauge_id", inplace=True)
    watersheds.index = watersheds.index.astype(str)

    # Load GRDC
    print(f"\nLoading GRDC from {args.grdc_dir}...")
    grdc_stations = load_grdc_stations(args.grdc_dir)

    # Match
    print("\nMatching GRDC → CAMELS-RU...")
    matches = match_grdc_to_camels(grdc_stations, gauges, watersheds, max_dist_km=args.max_dist)

    if not matches:
        print("No matches found!")
        return

    # Compare discharge
    print("\nComparing discharge time series...")
    results = []
    for m in matches:
        camels_id = m["camels_id"]
        compound_file = COMPOUND_DIR / f"{camels_id}.csv"
        if not compound_file.exists():
            continue

        df = pd.read_csv(compound_file, index_col="date", parse_dates=True)
        if "q_cms" not in df.columns:
            # Fall back to q_mm_day if q_cms not available
            if "q_mm_day" in df.columns and m["camels_area_km2"]:
                # Convert mm/day → m³/s: Q_cms = Q_mm * area_km2 * 1e6 / 86400 / 1000
                df["q_cms"] = (
                    pd.to_numeric(df["q_mm_day"], errors="coerce") * m["camels_area_km2"] / 86.4
                )
            else:
                continue

        camels_q = pd.to_numeric(df["q_cms"], errors="coerce").dropna()
        grdc_q = m["grdc_discharge"]

        # Filter to study period
        grdc_q = grdc_q.loc[PERIOD_START:PERIOD_END]
        camels_q = camels_q.loc[PERIOD_START:PERIOD_END]

        stats = compare_discharge(grdc_q, camels_q)

        row = {
            "grdc_no": m["grdc_no"],
            "camels_id": m["camels_id"],
            "grdc_station": m["grdc_station"],
            "grdc_river": m["grdc_river"],
            "distance_km": m["distance_km"],
            "area_ratio": m["area_ratio"],
            "grdc_area_km2": m["grdc_area_km2"],
            "camels_area_km2": m["camels_area_km2"],
        }
        row.update(stats)
        results.append(row)

    if not results:
        print("No overlapping discharge data found!")
        return

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("r", ascending=False)

    # Save
    out_path = args.output_dir / "grdc_validation.csv"
    results_df.to_csv(out_path, index=False)
    print(f"\nResults saved to {out_path}")

    # Print summary
    valid = results_df[results_df["r"].notna()]
    print(f"\n{'=' * 70}")
    print("GRDC VALIDATION SUMMARY")
    print(f"{'=' * 70}")
    print(f"Matched station pairs:  {len(results_df)}")
    print(f"With sufficient overlap: {len(valid)}")
    if len(valid) > 0:
        print(
            f"\nCorrelation (r):  median={valid['r'].median():.3f}  mean={valid['r'].mean():.3f}  range=[{valid['r'].min():.3f}, {valid['r'].max():.3f}]"
        )
        print(
            f"NSE:              median={valid['nse'].median():.3f}  mean={valid['nse'].mean():.3f}  range=[{valid['nse'].min():.3f}, {valid['nse'].max():.3f}]"
        )
        print(
            f"PBIAS (%):        median={valid['pbias'].median():.1f}  mean={valid['pbias'].mean():.1f}  range=[{valid['pbias'].min():.1f}, {valid['pbias'].max():.1f}]"
        )
        print(f"RMSE (m³/s):      median={valid['rmse'].median():.1f}  mean={valid['rmse'].mean():.1f}")
        print("\nPer-station results:")
        for _, row in valid.iterrows():
            print(
                f"  {row['grdc_no']:>8s} | {row['grdc_river']:20s} | {row['grdc_station']:25s} | "
                f"r={row['r']:.3f}  NSE={row['nse']:.3f}  PBIAS={row['pbias']:+.1f}%  "
                f"overlap={row['overlap_days']}d  dist={row['distance_km']}km  "
                f"area_ratio={row['area_ratio']}"
            )


if __name__ == "__main__":
    main()
