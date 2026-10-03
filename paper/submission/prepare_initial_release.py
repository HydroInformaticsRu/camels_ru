"""Build or --verify the first public v1.0 package; never overwrite an existing build.

Run from the repository: pixi run python paper/submission/prepare_initial_release.py
This normalizes prepublication version labels; it does not publish or recompute data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
revision = importlib.import_module("verify_release_revision")
NETCDFS = revision.NETCDFS
sha256 = revision.sha256
verify_manifest = revision.verify_manifest
logger = logging.getLogger(__name__)

SOURCE = ROOT / "release/CAMELS_RU_v1.1_cf19"
TARGET = ROOT / "release/CAMELS_RU_v1.0_submission"
ARCHIVE = Path(str(TARGET) + ".zip")
CHECKSUM = Path(str(ARCHIVE) + ".sha256")
SOURCE_MANIFEST_SHA256 = "c6b763e4a3b7f9f526eb6d03acc6619e2ef8ddc7ee79e323f18a6cd10ed30e3e"
HISTORY = (
    "Prepublication version label normalized to first public CAMELS-RU 1.0; "
    "all data, variable metadata and storage layouts preserved. "
    "Earlier 1.1 labels describe internal preparation, not a published release."
    " Reference corrected from in review to manuscript in preparation; not yet submitted."
)
SOURCE_REFERENCES = (
    "Abramov et al.: CAMELS-RU dataset description (Earth System Science Data, in review); "
    "processing code: https://github.com/HydroInformaticsRu/camels_ru"
)
REFERENCES = SOURCE_REFERENCES.replace(
    "(Earth System Science Data, in review)",
    "(manuscript in preparation for Earth System Science Data)",
)
SIDECARS = ("signature_crosswalk.json", "hydroatlas_metadata.json")
INTRO = """# CAMELS-RU v1.0 — first public release package (CF-1.9)

A large-sample hydroclimatic dataset for 3,353 Russian catchments following the CAMELS framework.

Prepared for the first public release; not yet published. The reserved Zenodo DOI is
10.5281/zenodo.22132299 (unpublished). Earlier local version labels were internal
prepublication build identifiers, not public releases. This package uses version 1.0.
The proposed CC BY 4.0 data licence remains subject to verification of the applicable
source redistribution terms; this package does not certify licence clearance or
author/journal approval. Processing code uses the repository MIT licence.

The NetCDFs declare CF-1.9 and use the `station` instance dimension with string
identifier `gauge_id(station)` and auxiliary coordinates `lat(station)` / `lon(station)`.
Stored int64 time and all other storage types are preserved. Numerical time series,
interpolation/provenance flags, grades, signatures, attributes and boundaries are
unchanged from the verified prepublication snapshot. See `CHANGELOG.md`.

"""
VERIFICATION = """Both sidecars describe public version 1.0. Historical build labels and the original
processing provenance are retained in `REVISION_PROVENANCE.json` and NetCDF history.
The preparation script verifies every raw and decoded NetCDF value and mask, variable
attributes, dimensions and storage layout against the source; only the global version,
manuscript preparation status in `references`, and appended history differ. The
manuscript is not yet submitted. CSV/GeoPackage files are byte-identical to the source.
`SHA256SUMS` exhaustively covers all other files. Archive verification reads and hashes
each ZIP entry against the package; it does not merely check archive filenames.

From the package directory, check file integrity with `sha256sum -c SHA256SUMS`.
From the code repository, reproduce the preservation and archive checks with
`pixi run python paper/submission/prepare_initial_release.py --verify` (requires the
retained source snapshot and this prepared package). CF compliance is checked
separately; declaring `Conventions` does not by itself establish compliance.

"""
CHANGELOG = """# CAMELS-RU v1.0 — first public release

Status: prepared for submission; unpublished. Reserved DOI: 10.5281/zenodo.22132299.
There has been no previous public release. Internal prepublication labels are retained
only as historical provenance, not as a public version history.

## Included

- Three CF-1.9 NetCDF files with `station` and `time` dimensions, string identifier
  `gauge_id(station)`, and station latitude/longitude coordinates. Data variables
  associate `gauge_id lat lon`; time keeps its int64 storage and standard/long names.
- Eight CSV/GeoPackage files containing attributes, boundaries, signatures, summaries,
  annual grades and flags, and forcing fill provenance.
- Signature definitions and qualified comparisons in `signature_crosswalk.json`;
  support, units and usability of 288 attribute columns in `hydroatlas_metadata.json`.
- README, historical revision provenance and an exhaustive SHA-256 manifest.

## Final preparation

The verified internal CF-1.9 snapshot was copied without recomputing any data. Only
global `dataset_version` (1.0), an appended history note, `references` manuscript status,
sidecar release labels and release documentation changed. The reference now states
manuscript in preparation, correcting a premature in-review label; it is not submitted.
Raw/decoded values, masks, all variable attributes,
dimensions, dtypes, chunks, filters and byte-identical CSV/GeoPackage files are verified
by `paper/submission/prepare_initial_release.py --verify` in the code repository.
Original processing provenance is nested intact in `REVISION_PROVENANCE.json`.

## Interpretation and status

No new harmonised signatures, categorical re-extraction or correction of upstream
aggregation is supplied. Invalid categorical means remain for provenance and must not
be rounded into classes. The GDP per-capita and stored HDI scale descriptions clarify
existing values. Grading remains a consistency screen, not independent validation.
CF compliance, source-rights evidence and author agreement are separate checks;
this package does not certify publication, licence clearance or journal approval.
"""


def readme() -> str:
    """Retain scientific guidance while replacing internal build-status text."""
    text = (SOURCE / "README.md").read_text()
    text = (
        INTRO + "## Metadata and interoperability" + text.split("## Metadata and interoperability", 1)[1]
    )
    start = text.index("Both sidecars describe the unchanged v1.0 values")
    end = text.index("## Contents", start)
    text = text[:start] + VERIFICATION + text[end:]
    return (
        text.replace("In this candidate,", "In this release,")
        .replace(
            "Scope of the v1.1 metadata amendment and unchanged-data guarantees to verify.",
            "First public release contents, preparation and preservation checks.",
        )
        .replace(
            "no publication or author approval is certified by this candidate",
            "the manuscript is not yet published",
        )
    )


def sidecar(name: str) -> dict:
    """Change release labels only; retain all scientific metadata entries."""
    value = json.loads((SOURCE / name).read_text())
    value["applies_to_release_versions"] = ["1.0"]
    if name == "hydroatlas_metadata.json":
        value["release_policy"] = value["release_policy"].replace(
            "Numerical attributes unchanged from v1.0",
            "Numerical attributes preserved from the prepublication snapshot",
        )
    return value


def verify() -> None:
    """Require exact preservation apart from the explicitly permitted metadata."""
    original, current = verify_manifest(SOURCE), verify_manifest(TARGET)
    assert set(original) == set(current) and len(current) == 16
    unchanged = [name for name in original if Path(name).suffix in {".csv", ".gpkg"}]
    assert len(unchanged) == 8
    for name in unchanged:
        assert original[name] == current[name], name
    for name in NETCDFS:
        with Dataset(SOURCE / name) as before, Dataset(TARGET / name) as after:
            assert not before.groups and not after.groups
            assert before.data_model == after.data_model
            assert list(before.dimensions) == list(after.dimensions)
            for dim in before.dimensions:
                assert len(before.dimensions[dim]) == len(after.dimensions[dim])
                assert before.dimensions[dim].isunlimited() == after.dimensions[dim].isunlimited()
            assert set(before.ncattrs()) == set(after.ncattrs())
            assert before.dataset_version == "1.1" and after.dataset_version == "1.0"
            assert after.history == before.history + "\n" + HISTORY
            assert before.references == SOURCE_REFERENCES and after.references == REFERENCES
            for key in before.ncattrs():
                if key not in {"dataset_version", "history", "references"}:
                    revision._same(before.getncattr(key), after.getncattr(key), f"{name}:{key}")
            assert list(before.variables) == list(after.variables)
            for key in before.variables:
                assert before.variables[key].shape == after.variables[key].shape
                revision._compare_variable(before.variables[key], after.variables[key], key, name)
        logger.info("PASS values, masks, attributes and storage: %s", name)
    for name in SIDECARS:
        assert json.loads((TARGET / name).read_text()) == sidecar(name), name
    assert (TARGET / "README.md").read_text() == readme()
    assert (TARGET / "CHANGELOG.md").read_text() == CHANGELOG
    provenance = json.loads((TARGET / "REVISION_PROVENANCE.json").read_text())
    assert provenance["dataset_version"] == "1.0"
    assert provenance["preparation"] == HISTORY
    assert provenance["numerical_changes"] == []
    assert provenance["netcdf_global_metadata_changes"] == ["dataset_version", "history", "references"]
    assert provenance["source_manifest"] == original
    assert provenance["source_manifest_sha256"] == sha256(SOURCE / "SHA256SUMS")
    assert provenance["source_manifest_text"] == (SOURCE / "SHA256SUMS").read_text()
    assert provenance["prepublication_provenance"] == json.loads(
        (SOURCE / "REVISION_PROVENANCE.json").read_text()
    )
    assert provenance["preparation_script_sha256"] == sha256(Path(__file__))
    expected = {f"CAMELS_RU_v1.0/{name}": digest for name, digest in current.items()}
    expected["CAMELS_RU_v1.0/SHA256SUMS"] = sha256(TARGET / "SHA256SUMS")
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert len(archive.namelist()) == len(expected) and set(archive.namelist()) == set(expected)
        for name, digest in expected.items():
            with archive.open(name) as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == digest, name
    assert CHECKSUM.read_text() == f"{sha256(ARCHIVE)}  {ARCHIVE.name}\n"
    logger.info("PASS 17 files, exhaustive manifests and streamed ZIP verification: %s", ARCHIVE.name)


def main() -> None:
    """Create a new package or check the existing package without modification."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify", action="store_true", help="Verify an existing package and ZIP without writing"
    )
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError("Run without -O: preservation checks require assertions")
    assert sha256(SOURCE / "SHA256SUMS") == SOURCE_MANIFEST_SHA256, "Unexpected source snapshot"
    original = verify_manifest(SOURCE)
    if args.verify:
        verify()
        return
    if any(path.exists() for path in (TARGET, ARCHIVE, CHECKSUM)):
        raise FileExistsError(
            "Build destination already exists; use --verify. No files were overwritten."
        )
    shutil.copytree(SOURCE, TARGET)
    for name in NETCDFS:
        with Dataset(TARGET / name, "r+") as dataset:
            assert dataset.references == SOURCE_REFERENCES, f"Unexpected source reference: {name}"
            dataset.dataset_version = "1.0"
            dataset.history += "\n" + HISTORY
            dataset.references = REFERENCES
    for name in SIDECARS:
        (TARGET / name).write_text(json.dumps(sidecar(name), indent=2, ensure_ascii=False) + "\n")
    (TARGET / "README.md").write_text(readme())
    (TARGET / "CHANGELOG.md").write_text(CHANGELOG)
    provenance = {
        "dataset_version": "1.0",
        "publication_status": "unpublished; first public release prepared",
        "reserved_doi": "10.5281/zenodo.22132299",
        "schema_revision": "cf19_station",
        "preparation": HISTORY,
        "repository": "https://github.com/HydroInformaticsRu/camels_ru",
        "preparation_repository_commit": subprocess.check_output(
            ["/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "preparation_script_sha256": sha256(Path(__file__)),
        "source_directory": str(SOURCE.relative_to(ROOT)),
        "source_manifest": original,
        "source_manifest_text": (SOURCE / "SHA256SUMS").read_text(),
        "source_manifest_sha256": sha256(SOURCE / "SHA256SUMS"),
        "prepublication_provenance": json.loads((SOURCE / "REVISION_PROVENANCE.json").read_text()),
        "numerical_changes": [],
        "netcdf_global_metadata_changes": ["dataset_version", "history", "references"],
    }
    (TARGET / "REVISION_PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n"
    )
    (TARGET / "SHA256SUMS").write_text(
        "".join(
            f"{sha256(path)}  {path.name}\n"
            for path in sorted(TARGET.iterdir())
            if path.name != "SHA256SUMS"
        )
    )
    with zipfile.ZipFile(ARCHIVE, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(TARGET.iterdir()):
            archive.write(path, f"CAMELS_RU_v1.0/{path.name}")
    CHECKSUM.write_text(f"{sha256(ARCHIVE)}  {ARCHIVE.name}\n")
    verify()


if __name__ == "__main__":
    main()
