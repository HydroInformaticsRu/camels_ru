"""Regenerate only the map figures used in the CAMELS-RU manuscript.

Runs the three notebooks (00, 02, 03) that produce spatial map figures.
No heavy computation is repeated — this just re-renders existing data.

Figures regenerated (maps only):
  1  fig_gauge_network.png        — NB00
  4  fig_precip_comparison.png    — NB03
  6  fig_water_balance.png        — NB03
  7  fig_hydro_signatures_1.png   — NB02
  8  fig_hydro_signatures_2.png   — NB02

Usage:
    pixi run python scripts/regenerate_paper_maps.py
"""

from pathlib import Path
import subprocess
import sys

NOTEBOOKS = [
    "notebooks/00_DataDescription.py",
    "notebooks/02_HydrologicalFinal.py",
    "notebooks/03_ForcingsFinal.py",
]

ROOT = Path(__file__).parent.parent


def main() -> None:
    """Run each notebook sequentially."""
    failed = []
    for nb in NOTEBOOKS:
        path = ROOT / nb
        print(f"\n{'=' * 60}")
        print(f"Running {nb} ...")
        print(f"{'=' * 60}")
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            print(f"  FAILED (exit {result.returncode})")
            failed.append(nb)
        else:
            print("  OK")

    print(f"\n{'=' * 60}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("All map figures regenerated successfully.")


if __name__ == "__main__":
    main()
