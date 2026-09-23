"""Check the labelled release view for legacy and CF station dimensions."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import numpy as np
import xarray as xr

from utils.release_io import open_release_dataset


def test_release_io() -> None:
    """Keep IDs, measurements, coordinates and file closing equivalent."""
    temp_root = Path(__file__).resolve().parents[1] / ".tmp"
    temp_root.mkdir(exist_ok=True)
    ids = ["00002", "1000001", "001"]
    values = np.array([[1.0, np.nan], [3.0, 4.0], [5.0, 6.0]], dtype=np.float32)
    original_open = xr.open_dataset
    with TemporaryDirectory(dir=temp_root) as tmp:
        for dim in ("gauge_id", "station"):
            source = xr.Dataset(
                {"discharge_mm": ((dim, "time"), values, {"units": "mm d-1"})},
                coords={
                    "gauge_id": (dim, ids, {"cf_role": "timeseries_id"}),
                    "time": np.array(["2008-01-01", "2008-01-02"], dtype="datetime64[ns]"),
                    "lat": (dim, [60.0, 61.0, 62.0]),
                    "lon": (dim, [30.0, 31.0, 32.0]),
                },
                attrs={"title": "test release"},
            )
            path = Path(tmp) / f"{dim}.nc"
            source.to_netcdf(path)
            raw = original_open(path)
            close = Mock(wraps=raw._close)
            raw.set_close(close)
            with patch("utils.release_io.xr.open_dataset", return_value=raw) as opener:
                with open_release_dataset(path) as actual:
                    opener.assert_called_once_with(path)
                    assert actual.gauge_id.values.tolist() == ids
                    assert actual.discharge_mm.dims == ("gauge_id", "time")
                    np.testing.assert_equal(actual.discharge_mm.values, values)
                    np.testing.assert_equal(actual.sel(gauge_id="001").discharge_mm.values, values[2])
                    np.testing.assert_equal(actual.sum("gauge_id").discharge_mm.values, [9.0, 10.0])
                    np.testing.assert_equal(
                        actual.reindex(gauge_id=ids[::-1]).discharge_mm.values, values[::-1]
                    )
                    np.testing.assert_equal(
                        actual.discharge_mm.transpose("gauge_id", "time").values, values
                    )
                    assert actual.attrs == source.attrs
                    assert actual.gauge_id.attrs == source.gauge_id.attrs
                    assert actual.discharge_mm.attrs == source.discharge_mm.attrs
                    np.testing.assert_equal(actual.lat.values, source.lat.values)
                    np.testing.assert_equal(actual.lon.values, source.lon.values)
                close.assert_called_once_with()
            with open_release_dataset(path, decode_times=False) as numeric_time:
                assert np.issubdtype(numeric_time.time.dtype, np.number)

        invalid = (
            (source.drop_vars("gauge_id"), "gauge_id(station)"),
            (source.assign_coords(gauge_id=("time", ["a", "b"])), "gauge_id(station)"),
            (source.assign_coords(gauge_id=("station", ["a", "a", "b"])), "unique"),
            (source.assign_coords(gauge_id=("station", ["a", "", "b"])), "nonmissing"),
            (source.assign_coords(gauge_id=("station", ["a", None, "b"])), "nonmissing"),
        )
        for bad, message in invalid:
            close = Mock()
            bad.set_close(close)
            with patch("utils.release_io.xr.open_dataset", return_value=bad):
                try:
                    open_release_dataset(path)
                except ValueError as error:
                    assert message in str(error), str(error)
                else:
                    raise AssertionError("Invalid station IDs must fail before selection")
            close.assert_called_once_with()


if __name__ == "__main__":
    test_release_io()
    print("Release reader checks passed.")
