"""Open either released station layout with labelled gauge_id indexing."""

from pathlib import Path
from typing import Any

import xarray as xr


def open_release_dataset(path: str | Path, **kwargs: Any) -> xr.Dataset:
    """Return a gauge-indexed view, retaining xarray options and close semantics.

    Legacy releases already use the gauge_id dimension. CF time-series releases
    store gauge_id(station); swapping that dimension changes no IDs or values.
    Callers must close the result or use it as a context manager, as with xarray.
    """
    dataset = xr.open_dataset(path, **kwargs)
    if "station" not in dataset.dims:
        return dataset
    try:
        if "gauge_id" not in dataset or dataset["gauge_id"].dims != ("station",):
            raise ValueError(f"{path}: station layout requires one-dimensional gauge_id(station)")
        ids = dataset["gauge_id"].to_index()
        if ids.hasnans or "" in ids:
            raise ValueError(f"{path}: gauge_id(station) must contain nonmissing IDs")
        if not ids.is_unique:
            raise ValueError(f"{path}: gauge_id(station) must contain unique IDs")
        labelled = dataset.swap_dims({"station": "gauge_id"})
        labelled.set_close(dataset.close)
        return labelled
    except Exception:
        dataset.close()
        raise
