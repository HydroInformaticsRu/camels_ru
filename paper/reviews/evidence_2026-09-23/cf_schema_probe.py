"""Synthetic metadata-only diagnosis; never reads or changes release data."""
from pathlib import Path
import json
import subprocess

from netCDF4 import Dataset
import numpy as np

ROOT = Path(__file__).resolve().parent
CHECKER = ROOT.parent / "essd_cf_checker/cache/cached-envs-v0/d0e019384e8a72d6/bin/compliance-checker"
results = {}
for dimension in ("gauge_id", "station"):
    path = ROOT / f"synthetic_cf19_{dimension}.nc"
    if path.exists():
        raise FileExistsError(path)
    with Dataset(path, "w") as ds:
        ds.setncatts({"Conventions": "CF-1.9", "featureType": "timeSeries",
                     "title": "SYNTHETIC checker diagnosis; not CAMELS-RU observations",
                     "history": "Created for a controlled schema test only"})
        ds.createDimension(dimension, 2)
        ds.createDimension("time", 2)
        ids = ds.createVariable("gauge_id", str, (dimension,))
        ids[:] = np.array(["101", "102"], dtype=object)
        ids.setncatts({"cf_role": "timeseries_id", "long_name": "Synthetic station identifier"})
        t = ds.createVariable("time", "i8", ("time",))
        t[:] = [0, 1]
        t.setncatts({"units": "days since 2008-01-01", "calendar": "proleptic_gregorian",
                    "standard_name": "time"})
        for name, values, standard, units in (
            ("lat", [50., 51.], "latitude", "degrees_north"),
            ("lon", [40., 41.], "longitude", "degrees_east"),
        ):
            v = ds.createVariable(name, "f8", (dimension,))
            v[:] = values
            v.setncatts({"standard_name": standard, "units": units})
        q = ds.createVariable("q", "f4", (dimension, "time"))
        q[:] = [[1., 2.], [3., 4.]]
        q.setncatts({"long_name": "Synthetic discharge", "units": "m3 s-1",
                    "coordinates": "gauge_id lat lon"})
    report = path.with_suffix(".json")
    result = subprocess.run([str(CHECKER), "--test=cf:1.9", "--criteria=strict",
                             "--format=json", f"--output={report}", str(path)],
                            text=True, capture_output=True)
    path.with_suffix(".log").write_text(result.stdout + result.stderr)
    results[dimension] = {"exit_code": result.returncode, "report": report.name,
                          "output": result.stdout + result.stderr}
print(json.dumps(results, indent=2))
(ROOT / "cf_schema_probe_results.json").write_text(json.dumps(results, indent=2) + "\n")
