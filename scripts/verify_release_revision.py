"""Verify a metadata-only CAMELS-RU amendment independently of the writer.

This checks numerical preservation and the enumerated amendment, not CF compliance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import geopandas as gpd
from netCDF4 import Dataset
import numpy as np

NETCDFS = ("camels_ru_discharge.nc", "camels_ru_forcing.nc", "camels_ru_water_level.nc")
SIGNATURES = {
    "q_mean",
    "runoff_ratio",
    "q_cv",
    "fdc_slope",
    "flashiness_index",
    "q05",
    "q95",
    "high_flow_freq",
    "high_flow_dur",
    "baseflow_index",
    "low_flow_freq",
    "low_flow_dur",
    "half_flow_date",
    "winter_flow_ratio",
    "aridity_index",
    "evaporative_index",
    "runoff_ratio_era5",
    "aridity_index_era5",
    "evaporative_index_era5",
}
INVALID_CLASSES = {
    "clz_cl_smj",
    "cls_cl_smj",
    "glc_cl_smj",
    "pnv_cl_smj",
    "wet_cl_smj",
    "tbi_cl_smj",
    "tec_cl_smj",
    "fmh_cl_smj",
    "fec_cl_smj",
    "lit_cl_smj",
    "gad_id_smj",
}
HISTORY_ENTRY = (
    "CAMELS-RU 1.1 metadata amendment: added station coordinates; original numerical data preserved."
)
COORDINATE_COMMENT = (
    "Gauge/outlet location, not a catchment centroid. Meteorological forcing remains "
    "basin-averaged; these coordinates do not describe point forcing."
)
PERMITTED_AMENDMENTS = {
    "netcdf_new_variables": ["lat(gauge_id)", "lon(gauge_id)"],
    "netcdf_existing_variable_attributes": [
        "coordinates: append lat lon to gauge-indexed data variables"
    ],
    "netcdf_global_attributes": ["dataset_version: 1.1", f"history: append {HISTORY_ENTRY}"],
    "replaced_files": ["README.md", "SHA256SUMS"],
    "added_files": [
        "signature_crosswalk.json",
        "hydroatlas_metadata.json",
        "CHANGELOG.md",
        "REVISION_PROVENANCE.json",
    ],
    "numerical_changes": [],
}


CF19_HISTORY_ENTRY = (
    HISTORY_ENTRY + " CF-1.9 schema: gauge_id dimension renamed to station; "
    "time names and gauge identifier associations added."
)
CF19_PERMITTED_AMENDMENTS = {
    **PERMITTED_AMENDMENTS,
    "netcdf_dimension_renames": {"gauge_id": "station"},
    "netcdf_new_variables": ["lat(station)", "lon(station)"],
    "netcdf_existing_variable_attributes": [
        "coordinates: append gauge_id lat lon to gauge-indexed data variables",
        "time.standard_name: time",
        "time.long_name: Time",
    ],
    "netcdf_global_attributes": [
        "dataset_version: 1.1",
        f"history: append {CF19_HISTORY_ENTRY}",
        "Conventions: CF-1.9",
    ],
}


def sha256(path: Path) -> str:
    """Hash file bytes without loading the whole file."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_manifest(directory: Path) -> dict[str, str]:
    """Require an exhaustive manifest of regular files, with safe relative names."""
    directory = directory.resolve(strict=True)
    manifest = directory / "SHA256SUMS"
    if manifest.is_symlink():
        raise ValueError("Symlink manifest is not a frozen source")
    hashes = {}
    for line in manifest.read_text().splitlines():
        digest, separator, name = line.partition("  ")
        path = Path(name)
        if (
            not separator
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
            or not name
            or path.is_absolute()
            or ".." in path.parts
            or name in hashes
            or name == "SHA256SUMS"
        ):
            raise ValueError(f"Invalid manifest line: {line!r}")
        target = directory / path
        if not target.is_file() or target.is_symlink() or sha256(target) != digest:
            raise ValueError(f"Checksum mismatch or unsafe file: {target}")
        hashes[name] = digest
    entries = list(directory.rglob("*"))
    if any(p.is_symlink() or (not p.is_file() and not p.is_dir()) for p in entries):
        raise ValueError("Symlinks and special files are not permitted in a frozen release")
    actual = {p.relative_to(directory).as_posix() for p in entries if p.is_file() and p != manifest}
    if not hashes or actual != set(hashes):
        raise ValueError(f"Manifest coverage mismatch: {actual ^ set(hashes)}")
    return hashes


def _same(left, right, label: str) -> None:
    try:
        np.testing.assert_array_equal(left, right)
    except AssertionError as error:
        raise ValueError(f"Changed {label}") from error


def _compare_variable(before, after, name: str, label: str, *, cf19: bool = False) -> None:
    dimensions = tuple("station" if cf19 and dim == "gauge_id" else dim for dim in before.dimensions)
    if (
        before.dtype != after.dtype
        or dimensions != after.dimensions
        or before.chunking() != after.chunking()
        or before.filters() != after.filters()
        or before.endian() != after.endian()
    ):
        raise ValueError(f"Changed layout/packing: {label}:{name}")
    attrs = {k: before.getncattr(k) for k in before.ncattrs()}
    if "gauge_id" in before.dimensions and name != "gauge_id":
        attrs["coordinates"] = " ".join(
            dict.fromkeys(
                str(attrs.get("coordinates", "")).split()
                + (["gauge_id"] if cf19 else [])
                + ["lat", "lon"]
            )
        )
    if cf19 and name == "time":
        attrs.update(standard_name="time", long_name="Time")
    if set(attrs) != set(after.ncattrs()):
        raise ValueError(f"Unexpected variable attributes: {label}:{name}")
    for key, value in attrs.items():
        _same(value, after.getncattr(key), f"{label}:{name}:{key}")
    # Chunk the first dimension to bound memory for the 3353 x 5844 arrays.
    slices = (slice(i, i + 128) for i in range(0, before.shape[0], 128)) if before.ndim else [Ellipsis]
    for selection in slices:
        for decoded in (False, True):
            before.set_auto_maskandscale(decoded)
            after.set_auto_maskandscale(decoded)
            a, b = before[selection], after[selection]
            if not decoded and not np.asarray(a).dtype.hasobject and a.tobytes() != b.tobytes():
                raise ValueError(f"Changed raw bytes: {label}:{name}")
            _same(np.ma.getmaskarray(a), np.ma.getmaskarray(b), f"{name} missingness")
            _same(
                np.ma.getdata(a),
                np.ma.getdata(b),
                f"{name} {'decoded' if decoded else 'raw'} values",
            )


def compare_netcdf(
    source: Path, revised: Path, *, require_version: bool = False, cf19: bool = False
) -> None:
    """Compare layout, attributes, raw storage values, decoded values and masks in chunks."""
    with Dataset(source) as old, Dataset(revised) as new:
        if old.groups or new.groups or old.data_model != new.data_model:
            raise ValueError(f"Changed/unsupported NetCDF container: {source.name}")
        old_dims = [
            ("station" if cf19 and k == "gauge_id" else k, len(v), v.isunlimited())
            for k, v in old.dimensions.items()
        ]
        new_dims = [(k, len(v), v.isunlimited()) for k, v in new.dimensions.items()]
        if old_dims != new_dims or list(new.variables) != [*old.variables, "lat", "lon"]:
            raise ValueError(f"Changed dimensions or variable ordering: {source.name}")
        old_attrs = {k: old.getncattr(k) for k in old.ncattrs()}
        expected_attrs = old_attrs | ({"Conventions": "CF-1.9"} if cf19 else {})
        if require_version:
            expected_attrs["dataset_version"] = "1.1"
            expected_attrs["history"] = (
                str(old_attrs.get("history", ""))
                + "\n"
                + (CF19_HISTORY_ENTRY if cf19 else HISTORY_ENTRY)
            ).lstrip("\n")
        if set(expected_attrs) != set(new.ncattrs()):
            raise ValueError(f"Unexpected global attributes: {source.name}")
        for key, value in expected_attrs.items():
            _same(value, new.getncattr(key), f"{source.name} global {key}")
        for name, before in old.variables.items():
            _compare_variable(before, new[name], name, source.name, cf19=cf19)
        for name, standard, units in (
            ("lat", "latitude", "degrees_north"),
            ("lon", "longitude", "degrees_east"),
        ):
            var = new[name]
            expected = {
                "standard_name": standard,
                "long_name": f"Gauge {standard}",
                "units": units,
                "comment": COORDINATE_COMMENT,
            }
            if (
                var.dimensions != (("station" if cf19 else "gauge_id"),)
                or var.dtype != np.dtype("float64")
                or set(var.ncattrs()) != set(expected)
            ):
                raise ValueError(f"Invalid coordinate variable: {name}")
            for key, value in expected.items():
                _same(value, var.getncattr(key), f"{name}:{key}")


def validate_metadata(metadata_dir: Path, release_dir: Path) -> None:
    """Check sidecar coverage and the eleven invalid category means."""
    with (release_dir / "camels_ru_attributes.csv").open() as stream:
        attributes = set(next(csv.reader(stream))) - {"gauge_id"}
    with (release_dir / "camels_ru_signatures.csv").open() as stream:
        signature_columns = set(next(csv.reader(stream)))
    if len(attributes) != 288 or not SIGNATURES <= signature_columns:
        raise ValueError("Unexpected baseline signature/attribute columns")
    for filename, expected in (
        ("signature_crosswalk.json", SIGNATURES),
        ("hydroatlas_metadata.json", attributes),
    ):
        metadata = json.loads((metadata_dir / filename).read_text())
        variables = metadata["variables"]
        names = [v["name"] for v in variables]
        if (
            metadata["schema_version"] != 1
            or metadata["applies_to_release_versions"] != ["1.0", "1.1"]
            or len(names) != len(set(names))
            or set(names) != expected
        ):
            raise ValueError(f"Incomplete or invalid metadata: {filename}")
        if filename == "hydroatlas_metadata.json":
            invalid = {v["name"] for v in variables if v.get("usability") == "invalid_category_mean"}
            if invalid != INVALID_CLASSES or any(
                v.get("recommended_for_analysis") is not False for v in variables if v["name"] in invalid
            ):
                raise ValueError(
                    "Eleven averaged category codes must be excluded from recommended analysis"
                )


def _verify_station_source(station_info: dict) -> gpd.GeoDataFrame:
    station_path = Path(station_info["path"])
    if sha256(station_path) != station_info["sha256"]:
        raise ValueError("Station source hash mismatch")
    stations = gpd.read_file(station_path)
    if (
        stations.crs is None
        or stations.crs.to_epsg() != 4326
        or str(stations.crs) != station_info["crs"]
        or len(stations) != 3353
        or station_info["count"] != 3353
        or stations.gauge_id.isna().any()
        or stations.gauge_id.astype(str).duplicated().any()
        or (stations.gauge_id.astype(str).str.strip() == "").any()
        or stations.geometry.isna().any()
        or stations.geometry.is_empty.any()
        or (stations.geom_type != "Point").any()
    ):
        raise ValueError("Invalid station reference")
    stations = stations.set_index(stations.gauge_id.astype(str))
    xy = np.array([stations.geometry.x, stations.geometry.y])
    if not np.isfinite(xy).all() or (np.abs(xy[0]) > 180).any() or (np.abs(xy[1]) > 90).any():
        raise ValueError("Station coordinates out of range")
    return stations


def _valid_digest(value, lengths=(64,)) -> bool:
    return (
        isinstance(value, str)
        and len(value) in lengths
        and all(char in "0123456789abcdef" for char in value)
    )


def _verify_code_provenance(code) -> None:
    if not isinstance(code, dict) or set(code) != {"repository", "manuscript_repository", "code_sha256"}:
        raise ValueError("Missing or incomplete code provenance")
    for name in ("repository", "manuscript_repository"):
        state = code[name]
        if (
            not isinstance(state, dict)
            or set(state) != {"commit", "dirty", "status_porcelain"}
            or not _valid_digest(state["commit"], (40, 64))
            or not isinstance(state["status_porcelain"], str)
            or type(state["dirty"]) is not bool
            or state["dirty"] != bool(state["status_porcelain"])
        ):
            raise ValueError(f"Invalid recorded git state: {name}")
    hashes = code["code_sha256"]
    if (
        not isinstance(hashes, dict)
        or set(hashes) != {"scripts/package_dataset.py", "scripts/verify_release_revision.py"}
        or not all(_valid_digest(value) for value in hashes.values())
    ):
        raise ValueError("Missing or invalid amendment code hashes")
    # These hashes identify actual working-tree code; a dirty commit alone cannot do so.


def _verify_metadata_sources(sources, current: dict[str, str]) -> None:
    if not isinstance(sources, dict) or set(sources) != {
        "signature_crosswalk.json",
        "hydroatlas_metadata.json",
        "README.md",
        "CHANGELOG.md",
    }:
        raise ValueError("Missing or incomplete amendment metadata sources")
    for name, record in sources.items():
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "sha256"}
            or not isinstance(record["path"], str)
            or "\0" in record["path"]
            or not Path(record["path"]).is_absolute()
            or not _valid_digest(record["sha256"])
            or current.get(name) != record["sha256"]
        ):
            raise ValueError(f"Invalid or mismatched amendment metadata source: {name}")


def verify_revision(source: Path, revised: Path) -> None:
    """Verify manifests, permitted amendments and frozen source values."""
    source, revised = source.resolve(strict=True), revised.resolve(strict=True)
    if source == revised or source in revised.parents or revised in source.parents:
        raise ValueError("Source and revised directories overlap")
    original, current = verify_manifest(source), verify_manifest(revised)
    provenance = json.loads((revised / "REVISION_PROVENANCE.json").read_text())
    cf19 = provenance.get("schema_revision") == "cf19_station"
    if "schema_revision" in provenance and not cf19:
        raise ValueError("Unknown amendment schema revision")
    permitted = CF19_PERMITTED_AMENDMENTS if cf19 else PERMITTED_AMENDMENTS
    _verify_code_provenance(provenance.get("code_provenance"))
    _verify_metadata_sources(provenance.get("metadata_sources"), current)
    if (
        provenance["dataset_version"] != "1.1"
        or provenance["source_manifest"] != original
        or provenance["source_manifest_sha256"] != sha256(source / "SHA256SUMS")
        or provenance["source_manifest_text"] != (source / "SHA256SUMS").read_text()
        or provenance["permitted_amendments"] != permitted
    ):
        raise ValueError("Incorrect baseline or permitted amendments in provenance")
    if set(current) != set(original) | set(PERMITTED_AMENDMENTS["added_files"]):
        raise ValueError("Unexpected candidate file set")
    for name, digest in original.items():
        if name not in {*NETCDFS, "README.md"} and current.get(name) != digest:
            raise ValueError(f"Changed original payload: {name}")
    stations = _verify_station_source(provenance["station_source"])
    for name in NETCDFS:
        compare_netcdf(source / name, revised / name, require_version=True, cf19=cf19)
        with Dataset(revised / name) as nc:
            ids = np.asarray(nc["gauge_id"][:]).astype(str)
            if len(ids) != 3353 or len(set(ids)) != 3353 or set(ids) != set(stations.index):
                raise ValueError(f"Incomplete station mapping: {name}")
            matched = stations.loc[ids]
            _same(nc["lat"][:], matched.geometry.y.to_numpy(), f"{name} station latitude")
            _same(nc["lon"][:], matched.geometry.x.to_numpy(), f"{name} station longitude")
    validate_metadata(revised, revised)
    print("PASS: manifests, station mapping, numerical preservation and enumerated metadata amendment")
    print("CF compliance and author approval remain separate checks.")


def main() -> None:
    """Run verification against the explicit source and candidate directories."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--revised-dir", type=Path, required=True)
    args = parser.parse_args()
    verify_revision(args.source_dir, args.revised_dir)


if __name__ == "__main__":
    main()
