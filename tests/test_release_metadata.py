"""Small metadata-amendment regression check; never touches a release directory.

Run: pixi run --as-is python tests/test_release_metadata.py
"""

import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

import geopandas as gpd
from netCDF4 import Dataset
import numpy as np
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import package_dataset as package  # noqa: E402
from package_dataset import (  # noqa: E402
    append_station_coordinates,
    checked_amendment_paths,
    station_coordinates,
)
from verify_release_revision import (  # noqa: E402
    NETCDFS,
    compare_netcdf,
    verify_manifest,
    verify_revision,
)


def rejects(call, message):
    try:
        call()
    except (ValueError, FileExistsError, AssertionError):
        return
    raise AssertionError(message)


def synthetic_amendment(tmp):
    """Exercise the full amendment on tiny arrays, using the checked-in sidecar schema."""
    source, candidate = tmp / "fixture", tmp / "candidate"
    source.mkdir()
    ids = [str(i) for i in range(3353)]
    stations = gpd.GeoDataFrame(
        {"gauge_id": ids[::-1]}, geometry=[Point(30, 60)] * len(ids), crs="EPSG:4326"
    )
    station_dir = tmp / "geometry"
    station_dir.mkdir()
    stations.to_file(station_dir / "camels_gauges.gpkg", driver="GPKG")
    for name in NETCDFS:
        with Dataset(source / name, "w") as nc:
            nc.createDimension("gauge_id", len(ids))
            nc.createDimension("time", 2)
            nc.createVariable("gauge_id", str, ("gauge_id",))[:] = np.array(ids, dtype=object)
            time = nc.createVariable("time", "i8", ("time",))
            time[:] = [0, 1]
            time.units = "days since 2008-01-01"
            time.calendar = "proleptic_gregorian"
            q = nc.createVariable("q", "i2", ("gauge_id", "time"), zlib=True, fill_value=-32768)
            q.scale_factor, q.add_offset = 0.1, 1.0
            values = np.ma.array(np.full((len(ids), 2), 2.5), mask=False)
            values.mask[1, 1] = True
            q[:] = values
    for stem, metadata in (
        ("attributes", "hydroatlas_metadata.json"),
        ("signatures", "signature_crosswalk.json"),
    ):
        variables = json.loads((ROOT / "paper" / "metadata" / metadata).read_text())["variables"]
        columns = ["gauge_id", *(item["name"] for item in variables)]
        (source / f"camels_ru_{stem}.csv").write_text(",".join(columns) + "\n")
    (source / "README.md").write_text("Synthetic frozen numerical baseline\n")
    shutil.copy2(station_dir / "camels_gauges.gpkg", source / "camels_ru_boundaries.gpkg")
    package.write_checksums(source)
    hashes = verify_manifest(source)
    previous = package.GEOM_DIR
    try:
        package.GEOM_DIR = station_dir
        package.amend_metadata(source, candidate)
        package.amend_metadata(source, tmp / "candidate_cf19", cf19=True)
    finally:
        package.GEOM_DIR = previous
    assert verify_manifest(source) == hashes
    verify_revision(source, candidate)
    cf19_candidate = tmp / "candidate_cf19"
    verify_revision(source, cf19_candidate)
    cf19_provenance_path = cf19_candidate / "REVISION_PROVENANCE.json"
    cf19_provenance_text = cf19_provenance_path.read_text()
    cf19_provenance = json.loads(cf19_provenance_text)
    assert cf19_provenance["schema_revision"] == "cf19_station"
    assert cf19_provenance["permitted_amendments"]["netcdf_dimension_renames"] == {"gauge_id": "station"}
    cf19_provenance.pop("schema_revision")
    cf19_provenance["permitted_amendments"] = json.loads(
        (candidate / "REVISION_PROVENANCE.json").read_text()
    )["permitted_amendments"]
    cf19_provenance_path.write_text(json.dumps(cf19_provenance))
    package.write_checksums(cf19_candidate)
    rejects(lambda: verify_revision(source, cf19_candidate), "CF19 falsely declared legacy accepted")
    cf19_provenance_path.write_text(cf19_provenance_text)
    package.write_checksums(cf19_candidate)
    provenance_path = candidate / "REVISION_PROVENANCE.json"
    original_provenance = provenance_path.read_text()
    docs = {name: (candidate / name).read_bytes() for name in ("README.md", "CHANGELOG.md")}
    broken = json.loads(original_provenance)
    broken["metadata_sources"] = {}
    broken.pop("code_provenance")
    provenance_path.write_text(json.dumps(broken))
    for name in docs:
        (candidate / name).write_text("Arbitrary replacement text\n")
    package.write_checksums(candidate)
    rejects(
        lambda: verify_revision(source, candidate), "missing provenance allowed replaced documentation"
    )
    provenance_path.write_text(original_provenance)
    package.write_checksums(candidate)
    rejects(lambda: verify_revision(source, candidate), "replaced documentation escaped digest binding")
    for name, content in docs.items():
        (candidate / name).write_bytes(content)
    recorded = json.loads(original_provenance)
    for keys, value in (
        (("schema_revision",), "unknown"),
        (("metadata_sources",), {}),
        (("metadata_sources", "README.md", "path"), ""),
        (("metadata_sources", "CHANGELOG.md", "sha256"), "invalid"),
        (("code_provenance", "code_sha256"), {}),
        (("code_provenance", "code_sha256", "scripts/package_dataset.py"), "invalid"),
        (("code_provenance", "repository", "commit"), "invalid"),
        (("code_provenance", "repository", "status_porcelain"), None),
        (
            ("code_provenance", "manuscript_repository", "dirty"),
            not recorded["code_provenance"]["manuscript_repository"]["dirty"],
        ),
    ):
        changed = json.loads(original_provenance)
        entry = changed
        for key in keys[:-1]:
            entry = entry[key]
        entry[keys[-1]] = value
        provenance_path.write_text(json.dumps(changed))
        package.write_checksums(candidate)
        rejects(lambda: verify_revision(source, candidate), f"invalid provenance accepted: {keys}")
    provenance_path.write_text(original_provenance)
    package.write_checksums(candidate)
    with Dataset(candidate / NETCDFS[0], "a") as nc:
        nc["q"][0, 0] = 10
    package.write_checksums(candidate)
    rejects(
        lambda: verify_revision(source, candidate),
        "tampered numerical value with valid manifest accepted",
    )


def main():
    scratch = ROOT / ".tmp" / "essd_revision_2026-09-23"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=scratch) as tmp:
        tmp = Path(tmp)
        stations = gpd.GeoDataFrame(
            {"gauge_id": ["b", "a"]}, geometry=[Point(30, 60), Point(40, 50)], crs="EPSG:4326"
        )
        lat, lon = station_coordinates(stations, ["a", "b"])
        np.testing.assert_array_equal(lat, [50, 60])
        np.testing.assert_array_equal(lon, [40, 30])
        rejects(lambda: station_coordinates(stations, ["a", "missing"]), "missing gauge accepted")
        rejects(lambda: station_coordinates(stations, ["a", "a"]), "duplicate target accepted")
        duplicate = stations.copy()
        duplicate["gauge_id"] = ["a", "a"]
        rejects(lambda: station_coordinates(duplicate, ["a"]), "duplicate source accepted")
        for missing_id in (None, ""):
            invalid_ids = stations.copy()
            invalid_ids.loc[0, "gauge_id"] = missing_id
            rejects(
                lambda invalid_ids=invalid_ids: station_coordinates(invalid_ids, ["a", "b"]),
                "empty source ID accepted",
            )
        for geometry in (
            [Point(), Point(40, 50)],
            [Point(181, 50), Point(40, 50)],
            [Point(float("nan"), 50), Point(40, 50)],
            [LineString([(0, 0), (1, 1)]), Point(40, 50)],
        ):
            invalid = stations.copy()
            invalid.geometry = geometry
            rejects(
                lambda invalid=invalid: station_coordinates(invalid, ["a", "b"]),
                "invalid coordinates accepted",
            )
        rejects(
            lambda: station_coordinates(stations.set_crs("EPSG:3857", allow_override=True), ["a", "b"]),
            "incorrect CRS accepted",
        )
        rejects(
            lambda: station_coordinates(stations.set_crs(None, allow_override=True), ["a", "b"]),
            "absent CRS accepted",
        )
        source = tmp / "source"
        source.mkdir()
        rejects(lambda: checked_amendment_paths(source, source / "child"), "nested output accepted")
        rejects(lambda: checked_amendment_paths(source, tmp), "ancestor output accepted")
        alias = tmp / "alias"
        alias.symlink_to(source, target_is_directory=True)
        rejects(lambda: checked_amendment_paths(source, alias / "child"), "resolved overlap accepted")
        existing = tmp / "existing"
        existing.mkdir()
        rejects(lambda: checked_amendment_paths(source, existing), "existing output accepted")
        assert checked_amendment_paths(source, tmp / "new") == (source, tmp / "new")
        (source / "SHA256SUMS").write_text("0" * 64 + "  payload.csv\n")
        (source / "payload.csv").write_text("x\n1\n")
        rejects(lambda: verify_manifest(source), "bad source checksum accepted")
        rejects(lambda: package.amend_metadata(source, tmp / "must_not_exist"), "bad source amended")
        assert not (tmp / "must_not_exist").exists()
        original, revised = tmp / "original.nc", tmp / "revised.nc"
        with Dataset(original, "w") as nc:
            nc.createDimension("gauge_id", 2)
            nc.createDimension("time", 3)
            ids = nc.createVariable("gauge_id", str, ("gauge_id",))
            ids[:] = np.array(["a", "b"], dtype=object)
            nc.createVariable("time", "i8", ("time",))[:] = [1, 2, 3]
            values = nc.createVariable("q", "i2", ("gauge_id", "time"), fill_value=-32768, zlib=True)
            values.scale_factor = 0.1
            values.add_offset = 1.0
            values[:] = np.ma.array(
                [[1, 2, 3], [4, 5, 6]], mask=[[False, True, False], [False, False, False]]
            )
            nc.createVariable("signed_zero", "f4", ("gauge_id",))[:] = [0.0, 0.0]
            nc.title = "Frozen original"
        cf19 = tmp / "cf19.nc"
        shutil.copy2(original, cf19)
        append_station_coordinates(cf19, stations, cf19=True)
        compare_netcdf(original, cf19, cf19=True)
        with Dataset(cf19) as nc:
            assert list(nc.dimensions) == ["station", "time"]
            assert nc["gauge_id"].dimensions == ("station",)
            assert nc["q"].dimensions == ("station", "time")
            assert nc["lat"].dimensions == nc["lon"].dimensions == ("station",)
            assert nc["q"].coordinates == "gauge_id lat lon"
            assert nc["time"].standard_name == "time" and nc["time"].long_name == "Time"
            assert nc["time"].dtype == np.dtype("int64")
            np.testing.assert_array_equal(nc["time"][:], [1, 2, 3])
            np.testing.assert_array_equal(nc["gauge_id"][:], ["a", "b"])
            assert nc.Conventions == "CF-1.9"
        rejects(lambda: compare_netcdf(original, cf19), "CF19 layout accepted as legacy")
        with Dataset(cf19, "a") as nc:
            nc.renameDimension("station", "wrong_station")
        rejects(lambda: compare_netcdf(original, cf19, cf19=True), "wrong instance dimension accepted")
        with Dataset(cf19, "a") as nc:
            nc.renameDimension("wrong_station", "station")
            nc["q"].coordinates = "lat lon"
        rejects(
            lambda: compare_netcdf(original, cf19, cf19=True), "missing identifier association accepted"
        )
        with Dataset(cf19, "a") as nc:
            nc["q"].coordinates = "gauge_id lat lon"
            nc.renameVariable("gauge_id", "station")
        rejects(
            lambda: compare_netcdf(original, cf19, cf19=True), "renamed identifier variable accepted"
        )
        shutil.copy2(original, revised)
        append_station_coordinates(revised, stations)
        rejects(
            lambda: compare_netcdf(original, revised, cf19=True), "unrenamed CF19 dimension accepted"
        )
        compare_netcdf(original, revised)
        with Dataset(revised) as nc:
            assert nc["q"].coordinates == "lat lon"
            np.testing.assert_array_equal(nc["lat"][:], [50, 60])
        with Dataset(revised, "a") as nc:
            nc["signed_zero"][0] = -0.0
        rejects(lambda: compare_netcdf(original, revised), "raw sign bit change accepted")
        with Dataset(revised, "a") as nc:
            nc["signed_zero"][0] = 0.0
            nc["q"].units = "changed"
        rejects(lambda: compare_netcdf(original, revised), "unexpected metadata accepted")
        with Dataset(revised, "a") as nc:
            nc["q"].delncattr("units")
            nc["q"][0, 0] = 99
        rejects(lambda: compare_netcdf(original, revised), "modified existing data accepted")
        synthetic_amendment(tmp)
    print("PASS: release metadata joins, safeguards, packed preservation and tamper detection")


if __name__ == "__main__":
    main()
