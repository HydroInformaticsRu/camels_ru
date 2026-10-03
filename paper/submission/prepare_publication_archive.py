"""Build the public v1.0 ZIP or --verify it, preserving all scientific data."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
from pathlib import Path
import re
import shutil
import sys
import zipfile

from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
revision = importlib.import_module("verify_release_revision")
SOURCE = ROOT / "release/CAMELS_RU_v1.0_submission"
TARGET = ROOT / "release/zenodo_upload/CAMELS_RU_v1.0"
ARCHIVE = Path(str(TARGET) + ".zip")
CHECKSUM = Path(str(ARCHIVE) + ".sha256")
SOURCE_MANIFEST = "75bff393ef9bd2f0bf7c8504b61100c6ca51204cfc298d2afc0eb500026a2edf"
FORCING_REFERENCE = (
    "precip_era5 = ERA5-Land de-accumulated total precipitation (corrected); "
    "precip_gpcp = GPCP v3.3. Both are provided for the forcing intercomparison of "
    "manuscript Sect. 6.3; precip_mswep (MSWEP v2.8) is the recommended primary forcing."
)
PUBLIC_REFERENCE = FORCING_REFERENCE.replace("Sect. 6.3", 'section "Forcing plausibility"')
INTRO = """# CAMELS-RU v1.0

A large-sample hydroclimatic dataset for 3,353 Russian catchments following the CAMELS framework.

Dataset DOI: https://doi.org/10.5281/zenodo.22132299

The three NetCDF files use CF-1.9, with a `station` instance dimension, string
identifier `gauge_id(station)`, auxiliary coordinates `lat(station)` / `lon(station)`,
and int64 time storage. See the file inventory and joining guidance below.

## Licence and source attribution

CC BY 4.0 is the licence selected for the CAMELS-RU deposit:
https://creativecommons.org/licenses/by/4.0/ . Processing code uses the repository
MIT licence. Retain attribution to the dataset authors and the original data sources.

The discharge and water-level observations originate from AIS GMVO, Rosvodresursy
and the Roshydromet gauging network. Rosvodresursy's published open-data terms permit
copying, distribution, modification and commercial reuse subject to lawful use,
non-distortion and source attribution:
https://voda.gov.ru/otkrytoe-agentstvo/opendata/ (accessed 3 October 2026).
Rosvodresursy identifies state water-monitoring (GMVO) information among its open-data
resources at https://voda.gov.ru/press-tsenter/news/federalnye/557689/ . These published
terms provide the cited basis for reuse of the observations. The deposit's CC BY 4.0
selection does not replace the source terms or assert that Rosvodresursy itself
licensed its observations under CC BY 4.0. Processing and alterations are documented
below and in the file metadata; cite the original sources as well as CAMELS-RU.

"""
INTEGRITY = """Both sidecars describe version 1.0. `REVISION_PROVENANCE.json` records processing
history, source checksums, code revisions and the metadata changes used to prepare
this package. Its relative source paths identify provenance inputs, not additional
files required to load the dataset. `SHA256SUMS` covers all other files in the package.
Check integrity from this directory with `sha256sum -c SHA256SUMS`.

"""
CHANGELOG = """# CAMELS-RU v1.0

DOI: https://doi.org/10.5281/zenodo.22132299

## Release contents

- Daily discharge, water level and meteorological forcing in three CF-1.9 NetCDFs.
- Catchment boundaries, attributes, signatures, annual grades and flags, summaries
  and forcing-fill provenance in eight CSV/GeoPackage files.
- Signature definitions and attribute interpretation guidance in two JSON sidecars.
- README, processing provenance and an exhaustive SHA-256 manifest.

## Metadata and interpretation

NetCDFs use `station` and `time` dimensions, `gauge_id(station)` identifiers and
latitude/longitude auxiliary coordinates. The forcing metadata refers to the
manuscript section "Forcing plausibility" by title. Processing provenance preserves
source-file checksums, code revisions and historical uncommitted-build indicators;
machine-specific path prefixes and raw working-tree listings are omitted.

No numerical data, flags, grades, thresholds, eligibility rules or scientific
metadata definitions were changed when assembling this archive. Invalid categorical
attribute means remain for provenance and must not be rounded into classes. The
signature crosswalk describes qualified comparisons, not harmonised signatures.
Grading and water-balance screens are consistency diagnostics, not independent
validation of observational accuracy. Consult the README and sidecars before use.
"""
FORBIDDEN = re.compile(
    r"/home/|/media/|/tmp/|token=|eyJ[A-Za-z0-9_-]{15,}\."
    r'|"status_porcelain"\s*:|(?m:^ M |^\?\? )'
    r"|\bTBD\b|\[CITE\]|licence clearance|author/journal approval|submission gate",
    re.IGNORECASE,
)


def readme() -> str:
    """Retain scientific guidance and replace internal release-management prose."""
    text = (SOURCE / "README.md").read_text()
    text = (
        INTRO + "## Metadata and interoperability" + text.split("## Metadata and interoperability", 1)[1]
    )
    start, end = text.index("Both sidecars describe public version"), text.index("## Contents")
    text = text[:start] + INTEGRITY + text[end:]
    text = text.replace(
        "| `CHANGELOG.md` | Markdown | First public release contents, "
        "preparation and preservation checks. |",
        "| `CHANGELOG.md` | Markdown | Release contents and metadata notes. |\n"
        "| `README.md` | Markdown | Dataset documentation, licence, citation and usage guidance. |\n"
        "| `REVISION_PROVENANCE.json` | JSON | Source checksums, "
        "processing history and code revisions. |\n"
        "| `SHA256SUMS` | Text | SHA-256 checksums of the other 16 package files. |",
    )
    start, end = text.index("- **Missing data:**"), text.index("\n\n## Identifiers")
    text = (
        text[:start]
        + (
            "- **Missing data:** Missing continuous observations and forcing values use `NaN`. "
            "Categorical flags are separate: `quality_flag = 3` marks missing observations; "
            "`gauge_type = -1`, `stage_discharge_screen = -1` and "
            "`specific_discharge_anomaly = -1` are documented no-record/not-assessed classes. "
            "Their codes must not be interpreted as continuous measurements."
        )
        + text[end:]
    )
    return text.replace(
        "1. The final author-approved CAMELS-RU paper citation when available; "
        "the manuscript is not yet published",
        "1. Abramov, D. V., Maximov, Y., Tsyplenkov, A., and Moreido, V. (2026): "
        "CAMELS-RU: hydrometeorological time series and catchment attributes for 3353 Russian "
        "catchments, 2008–2023, version 1.0. Zenodo [data set]. https://doi.org/10.5281/zenodo.22132299",
    )


def hydroatlas() -> dict:
    """Remove only the local copy's location, retaining the public source URLs."""
    metadata = json.loads((SOURCE / "hydroatlas_metadata.json").read_text())
    assert (
        metadata["source"].pop("local_dictionary_checked")
        == "data/World/docs/BasinATLAS_Catalog_v10.pdf"
    )
    return metadata


def provenance() -> dict:
    """Project the historical record without losing hashes or dirty-build evidence."""
    original = json.loads((SOURCE / "REVISION_PROVENANCE.json").read_text())
    original.pop("publication_status")
    original["doi"] = original.pop("reserved_doi")
    historical = original["prepublication_provenance"]
    prefix = "/home/dmbrmv/Development/camels_ru/"
    assert historical["source_directory"].startswith(prefix)
    historical["source_directory"] = historical["source_directory"].removeprefix(prefix)
    for item in historical["metadata_sources"].values():
        assert item["path"].startswith(prefix)
        item["path"] = item["path"].removeprefix(prefix)
    assert (
        historical["station_source"]["path"]
        == "/media/dmbrmv/ssd_2tb/CAMELS_RU/geometry/camels_gauges.gpkg"
    )
    historical["station_source"]["path"] = "data/CAMELS_RU/geometry/camels_gauges.gpkg"
    for name in ("repository", "manuscript_repository"):
        repository = historical["code_provenance"][name]
        status = repository.pop("status_porcelain")
        assert repository["dirty"] is True and status
        repository["status_porcelain_sha256"] = hashlib.sha256(status.encode()).hexdigest()
    return {
        "dataset_version": "1.0",
        "doi": "10.5281/zenodo.22132299",
        "source_directory": str(SOURCE.relative_to(ROOT)),
        "source_manifest": revision.verify_manifest(SOURCE),
        "source_manifest_sha256": SOURCE_MANIFEST,
        "original_provenance_sha256": revision.sha256(SOURCE / "REVISION_PROVENANCE.json"),
        "archive_preparation_script": str(Path(__file__).resolve().relative_to(ROOT)),
        "archive_preparation_script_sha256": revision.sha256(Path(__file__)),
        "historical_provenance": original,
        "changes": {
            "README.md": "Reader documentation, citation, inventory and source-licence attribution.",
            "CHANGELOG.md": "Reader-facing release notes.",
            "hydroatlas_metadata.json": (
                "Remove source.local_dictionary_checked; scientific entries unchanged."
            ),
            "REVISION_PROVENANCE.json": (
                "Relative paths and hashed working-tree listings; dirty flags retained."
            ),
            "camels_ru_forcing.nc": {
                "global_attribute": "alt_precip_sources",
                "before": FORCING_REFERENCE,
                "after": PUBLIC_REFERENCE,
            },
            "SHA256SUMS": "Regenerated for package contents.",
        },
        "numerical_changes": [],
    }


def verify() -> None:
    """Verify unchanged science, approved metadata changes, safety and ZIP contents."""
    assert revision.sha256(SOURCE / "SHA256SUMS") == SOURCE_MANIFEST
    before_hashes, after_hashes = revision.verify_manifest(SOURCE), revision.verify_manifest(TARGET)
    assert set(before_hashes) == set(after_hashes) and len(after_hashes) == 16
    assert all(path.is_file() and not path.name.startswith(".") for path in TARGET.iterdir())
    unchanged = [name for name in before_hashes if Path(name).suffix in {".csv", ".gpkg"}]
    assert len(unchanged) == 8
    for name in [
        *unchanged,
        "signature_crosswalk.json",
        "camels_ru_discharge.nc",
        "camels_ru_water_level.nc",
    ]:
        assert before_hashes[name] == after_hashes[name], name
    for name in revision.NETCDFS:
        with Dataset(SOURCE / name) as before, Dataset(TARGET / name) as after:
            assert not before.groups and not after.groups and before.data_model == after.data_model
            assert list(before.dimensions) == list(after.dimensions)
            for key in before.dimensions:
                assert len(before.dimensions[key]) == len(after.dimensions[key])
                assert before.dimensions[key].isunlimited() == after.dimensions[key].isunlimited()
            assert set(before.ncattrs()) == set(after.ncattrs())
            for key in before.ncattrs():
                expected = before.getncattr(key)
                if name == "camels_ru_forcing.nc" and key == "alt_precip_sources":
                    assert expected == FORCING_REFERENCE
                    expected = PUBLIC_REFERENCE
                revision._same(expected, after.getncattr(key), f"{name}:{key}")
                assert not FORBIDDEN.search(str(after.getncattr(key))), f"{name}:{key}"
            assert list(before.variables) == list(after.variables)
            for key in before.variables:
                assert before.variables[key].shape == after.variables[key].shape
                revision._compare_variable(before.variables[key], after.variables[key], key, name)
                for attribute in after.variables[key].ncattrs():
                    assert not FORBIDDEN.search(str(after.variables[key].getncattr(attribute)))
        logging.info("PASS numerical, mask, storage and metadata checks: %s", name)
    assert (TARGET / "README.md").read_text() == readme()
    assert (TARGET / "CHANGELOG.md").read_text() == CHANGELOG
    assert json.loads((TARGET / "hydroatlas_metadata.json").read_text()) == hydroatlas()
    assert json.loads((TARGET / "REVISION_PROVENANCE.json").read_text()) == provenance()
    for path in (*TARGET.glob("*.md"), *TARGET.glob("*.json")):
        assert not FORBIDDEN.search(path.read_text()), path.name
    contents = readme().split("## Contents\n", 1)[1].split("## Dimensions\n", 1)[0]
    inventory = set(re.findall(r"^\| `([^`]+)` \|", contents, re.MULTILINE))
    assert inventory == set(after_hashes) | {"SHA256SUMS"}
    expected = {f"CAMELS_RU_v1.0/{name}": digest for name, digest in after_hashes.items()}
    expected["CAMELS_RU_v1.0/SHA256SUMS"] = revision.sha256(TARGET / "SHA256SUMS")
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert len(archive.namelist()) == len(expected) and set(archive.namelist()) == set(expected)
        for name, digest in expected.items():
            with archive.open(name) as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == digest, name
    assert CHECKSUM.read_text() == f"{revision.sha256(ARCHIVE)}  {ARCHIVE.name}\n"
    logging.info(
        "PASS all 17 files, provenance projection, public metadata scan and streamed ZIP hashes"
    )


def main() -> None:
    """Create a new archive or verify it without changing any files."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError("Run without -O: verification requires assertions")
    assert revision.sha256(SOURCE / "SHA256SUMS") == SOURCE_MANIFEST
    revision.verify_manifest(SOURCE)
    if args.verify:
        verify()
        return
    if any(path.exists() for path in (TARGET, ARCHIVE, CHECKSUM)):
        raise FileExistsError("Public build already exists; use --verify. No files overwritten.")
    shutil.copytree(SOURCE, TARGET)
    with Dataset(TARGET / "camels_ru_forcing.nc", "r+") as dataset:
        assert dataset.alt_precip_sources == FORCING_REFERENCE
        dataset.alt_precip_sources = PUBLIC_REFERENCE
    (TARGET / "README.md").write_text(readme())
    (TARGET / "CHANGELOG.md").write_text(CHANGELOG)
    for name, metadata in (
        ("hydroatlas_metadata.json", hydroatlas()),
        ("REVISION_PROVENANCE.json", provenance()),
    ):
        (TARGET / name).write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    (TARGET / "SHA256SUMS").write_text(
        "".join(
            f"{revision.sha256(path)}  {path.name}\n"
            for path in sorted(TARGET.iterdir())
            if path.name != "SHA256SUMS"
        )
    )
    with zipfile.ZipFile(ARCHIVE, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(TARGET.iterdir()):
            archive.write(path, f"CAMELS_RU_v1.0/{path.name}")
    CHECKSUM.write_text(f"{revision.sha256(ARCHIVE)}  {ARCHIVE.name}\n")
    verify()


if __name__ == "__main__":
    main()
