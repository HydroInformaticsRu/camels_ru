"""Regression test: ERA5 temp fill selection must follow forcing_notes, not disk.

Reproduces the 2023 ERA5-Land hardening item 3 (2026-06-23 triad
investigation): ``package_forcing`` chose the gap-filled CSV by bare file
existence (``era5_land_filled/<gid>.csv`` exists -> use it). A stale
climatology-filled CSV left behind from an earlier run would then ship into
``forcing.nc`` while ``forcing_notes.json`` -- the authoritative fill record,
and the per-gauge provenance shown to users -- says no fill was applied.

Selection must key on ``forcing_notes`` membership and ignore the filesystem.

Run: ``pixi run python tests/test_forcing_fill_selection.py``
Exits 0 on success, non-zero on regression.
"""

from pathlib import Path
import sys
import tempfile

sys.path.append(str(Path(__file__).parent.parent))
import scripts.package_dataset as pkg  # noqa: E402


def test_filled_csv_used_only_for_gauges_in_notes() -> None:
    """A gauge in forcing_notes reads the filled CSV; others read the base CSV."""
    notes = {"filled_gauge": "ERA5-Land 2023 gap filled with climatology (7 days)"}

    filled = pkg._select_era5_temp_file("filled_gauge", notes)
    assert filled == pkg.ERA5_FILLED_DIR / "filled_gauge.csv", (
        "a gauge listed in forcing_notes must read the gap-filled CSV"
    )

    clean = pkg._select_era5_temp_file("clean_gauge", notes)
    assert clean == pkg.ERA5_DIR / "clean_gauge.csv", (
        "a gauge absent from forcing_notes must read the base ERA5-Land CSV"
    )


def test_stale_filled_csv_is_ignored_when_not_in_notes() -> None:
    """A leftover filled CSV must NOT be selected if the gauge is not in notes."""
    with tempfile.TemporaryDirectory() as tmp:
        filled_dir = Path(tmp) / "era5_land_filled"
        base_dir = Path(tmp) / "era5_land"
        filled_dir.mkdir()
        base_dir.mkdir()
        # A stale climatology-filled CSV left on disk for a gauge with no fill note.
        (filled_dir / "stale_gauge.csv").write_text("date,t_mean\n2023-01-01,0.0\n")

        orig_filled, orig_base = pkg.ERA5_FILLED_DIR, pkg.ERA5_DIR
        try:
            pkg.ERA5_FILLED_DIR = filled_dir
            pkg.ERA5_DIR = base_dir
            selected = pkg._select_era5_temp_file("stale_gauge", forcing_notes={})
        finally:
            pkg.ERA5_FILLED_DIR, pkg.ERA5_DIR = orig_filled, orig_base

    assert selected == base_dir / "stale_gauge.csv", (
        "selection consulted the filesystem: a stale filled CSV was chosen "
        "despite the gauge being absent from forcing_notes"
    )


if __name__ == "__main__":
    test_filled_csv_used_only_for_gauges_in_notes()
    test_stale_filled_csv_is_ignored_when_not_in_notes()
    print("PASS: test_forcing_fill_selection")
