# Metadata amendment validation

Validation date: 23 September 2026. `release/CAMELS_RU_v1.1_cf19/` is a local,
unpublished metadata-amendment candidate derived from the frozen v1.0 package.
It has no new DOI. These results describe the identified files, not publication,
redistribution permission, or independent validation of observational accuracy.

## CF checks

IOOS Compliance Checker **6.1.0**, with `--test=cf:1.9 --criteria=strict`, completed
successfully for all three candidate NetCDF files. Each process exited 0, with no
reported high-, medium-, or low-priority findings; no checks were suppressed and
the checker was not patched.

| File | Points passed / assessed |
|------|--------------------------|
| `camels_ru_discharge.nc` | 215 / 215 |
| `camels_ru_forcing.nc` | 373 / 373 |
| `camels_ru_water_level.nc` | 265 / 265 |

The candidate uses the instance dimension `station`, the string identifier
`gauge_id(station)`, and auxiliary `lat(station)` / `lon(station)` coordinates.
It declares CF-1.9, retains int64 time, and adds time-name metadata and explicit
identifier/coordinate associations. Forcing values remain basin averages; station
coordinates locate gauge outlets.

The earlier `CAMELS_RU_v1.1` candidate is distinct and did **not** pass CF-1.8
checks. All three checks exited 2: int64 time and time-name metadata generated
findings, and the same-name string identifier `gauge_id(gauge_id)` triggered a
checker exception. The exception alone is not a standards verdict. The failed
candidate and frozen v1.0 were preserved; successful CF-1.9 results must not be
attributed to either of them.

## Numerical preservation and file identity

The repository verifier compared every original NetCDF variable in raw and
decoded form, including raw numerical bytes, missing-value masks, identifiers,
ordering, storage types, packing, compression filters, and chunk layout. It permits
only the documented dimension-name mapping and enumerated metadata additions.
All eight existing CSV/GeoPackage files are byte-identical to v1.0. No discharge,
forcing, stage, provenance flag, grade, signature, attribute, or boundary was
recalculated. The strict Grade A definition and grading thresholds are unchanged.
The manuscript macro verifier passed **398 numerical checks** for the preferred
candidate; this establishes numerical agreement, not scientific validity.

All manifest entries passed checksum verification. The hashes below identify each
package's `SHA256SUMS` file, not the package directory or a publication DOI.

| Package | Manifest entries | SHA-256 of `SHA256SUMS` |
|---------|------------------|------------------------|
| `CAMELS_RU_v1.0` | 12 | `947bb60d6b6e70605037fb72712d8bac7387bb16b37b317b6864a48cb22c1c7e` |
| `CAMELS_RU_v1.1` | 16 | `84c66d60281ecac55924db75aa2ba25b6006ad1d44a10f736543ef2665305a42` |
| `CAMELS_RU_v1.1_cf19` | 16 | `c6b763e4a3b7f9f526eb6d03acc6619e2ef8ddc7ee79e323f18a6cd10ed30e3e` |

## Reproduce the checks

Run from the repository root with the corresponding packages present under
`release/` and the manuscript checkout available at `paper/overleaf/`. Release
files are not distributed through Git. The macro verifier also reads the tracked
scientific audit tables in `paper/tables/` and `results/hess_quality/`.

```bash
pixi run --as-is python scripts/verify_release_revision.py --source-dir release/CAMELS_RU_v1.0 --revised-dir release/CAMELS_RU_v1.1_cf19
pixi run --as-is python scripts/verify_release_revision.py --source-dir release/CAMELS_RU_v1.0 --revised-dir release/CAMELS_RU_v1.1
pixi run --as-is python scripts/verify_macros.py --release-dir release/CAMELS_RU_v1.1_cf19
```

The following assumes `compliance-checker` 6.1.0 is already available on `PATH`.
It writes fresh reports without modifying release files:

```bash
mkdir -p .tmp/cf_validation/tmp .tmp/cf_validation/cache
for name in discharge forcing water_level; do
  TMPDIR="$PWD/.tmp/cf_validation/tmp" \
  XDG_CACHE_HOME="$PWD/.tmp/cf_validation/cache" \
  compliance-checker --test=cf:1.9 --criteria=strict --format=json \
    --output=".tmp/cf_validation/${name}.json" \
    "release/CAMELS_RU_v1.1_cf19/camels_ru_${name}.nc" \
    > ".tmp/cf_validation/${name}.log" 2>&1 || exit 1
done
```

The [signature crosswalk](signature_crosswalk.json) and
[HydroATLAS metadata](hydroatlas_metadata.json) qualify the unchanged values in both
v1.0 and the candidate. They do not harmonise signatures with other CAMELS datasets
or replace the invalid averaged categorical codes.
