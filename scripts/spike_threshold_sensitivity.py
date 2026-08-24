"""How many gauges the implausible-spike flag catches at 5 vs 8 sigma (Sect. 4.1.1).

Sect. 4.1.1 defends the 8-sigma outlier threshold on the grounds that a tighter
threshold "flags most gauges". That was asserted from spot checks and never
quantified, so this script measures it: it runs the production detector,
``quality.anomaly_detection.detect_implausible_spikes``, unchanged over the
released discharge at both thresholds and counts the gauges that pick up at
least one flagged value.

Using the production function rather than a reimplementation is the point --
a vectorised copy would drift from the code that actually graded the release.

Writes ``paper/tables/spike_threshold_sensitivity.csv`` for verify_macros.py.

Run: ``pixi run python scripts/spike_threshold_sensitivity.py``
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from quality.anomaly_detection import detect_implausible_spikes  # noqa: E402

RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
OUT = REPO / "paper" / "tables" / "spike_threshold_sensitivity.csv"

THRESHOLDS = (5.0, 8.0)


def main() -> None:
    """Count gauges carrying at least one spike at each sigma threshold."""
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        discharge = ds["discharge_m3s"].values
        gauge_ids = [str(g) for g in ds["gauge_id"].values]
        time = pd.to_datetime(ds["time"].values)

    # Only gauges that actually carry discharge can be assessed for spikes.
    assessed = [i for i, _ in enumerate(gauge_ids) if np.isfinite(discharge[i]).any()]
    print(f"gauges with discharge: {len(assessed)}")

    rows = []
    for threshold in THRESHOLDS:
        flagged = 0
        for i in assessed:
            series = pd.Series(discharge[i], index=time)
            if detect_implausible_spikes(series, sigma_threshold=threshold):
                flagged += 1
        share = 100 * flagged / len(assessed)
        rows.append(
            {
                "sigma_threshold": threshold,
                "gauges_assessed": len(assessed),
                "gauges_flagged": flagged,
                "pct_flagged": share,
            }
        )
        print(f"  {threshold:.0f} sigma: {flagged} of {len(assessed)} gauges flagged ({share:.1f}%)")

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
