"""Self-check for scripts/era5_hourly_to_daily.py (UTC-day reduction, K -> degC)."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from era5_hourly_to_daily import reduce_hourly  # noqa: E402


def main() -> None:
    times = pd.date_range("2020-01-01", periods=48, freq="h")
    t2m = xr.DataArray(
        273.15 + np.concatenate([np.linspace(-5, 5, 24), np.linspace(0, 10, 24)]),
        dims=["time"],
        coords={"time": times},
        name="t2m",
    )
    out = reduce_hourly(xr.Dataset({"t2m": t2m}))
    assert out.sizes["time"] == 2, "two UTC days expected"
    assert abs(float(out["t_mean"].isel(time=0)) - 0.0) < 1e-9
    assert abs(float(out["t_min"].isel(time=0)) - (-5.0)) < 1e-9
    assert abs(float(out["t_max"].isel(time=1)) - 10.0) < 1e-9
    print("OK - era5_hourly_to_daily reduction verified")


if __name__ == "__main__":
    main()
