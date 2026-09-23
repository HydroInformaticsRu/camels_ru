# Concrete v1.1 metadata amendment — approved and executed

The user approved this concrete amendment and isolated checker installation. The
build and numerical-equivalence checks passed; strict CF-1.8 checking did not pass.
See `CF_VALIDATION_2026-09-23.md` for the original results. The user subsequently
approved the separate follow-up; its successful build and checks are recorded in
`CF19_VALIDATION_2026-09-23.md`. This record preserves the first amendment scope.
No commit, push, upload, archival publication or journal submission was authorised.

## Exact input and destination

- Frozen input: `release/CAMELS_RU_v1.0/` (all 12 manifest entries verified unchanged).
- Source `SHA256SUMS` SHA-256:
  `947bb60d6b6e70605037fb72712d8bac7387bb16b37b317b6864a48cb22c1c7e`.
- New destination: `release/CAMELS_RU_v1.1/`, absent at approval and now created locally.
- The writer refuses an existing destination, source/output overlap, incomplete
  manifests, invalid station joins, or incomplete metadata.

## Permitted changes

1. Copy the complete frozen input, preserving the original directory.
2. Append float64 `lat(gauge_id)` and `lon(gauge_id)` to each of the three NetCDFs;
   associate gauge-indexed data with these coordinates and add version/history
   metadata. Existing arrays, ordering, dimensions, missingness, flags, storage
   types and packing remain unchanged. Coordinates locate gauges, not point forcing.
3. Replace the copied README with `paper/metadata/README_v1.1.md`.
4. Add `signature_crosswalk.json`, `hydroatlas_metadata.json`, `CHANGELOG.md` and
   `REVISION_PROVENANCE.json` from the reviewed sources/provenance recorder.
5. Write the new checksum manifest and run complete content-equivalence verification.

The eight existing CSV/GeoPackage files remain byte-identical. Eleven averaged
categorical codes remain stored unchanged but are explicitly excluded as category
identifiers. No signatures, grades, filled values or attributes are recomputed.

The read-only real-data preflight verified complete station joins for all three
3353-by-5844 NetCDF grids. Source points have explicit EPSG:4326 CRS and finite
coordinates (latitude 41.410733872507485–72.9891369112369, longitude
19.922287798704144–174.388533611111). These are structural/data-join checks, not an
independent survey of geographic accuracy. Detailed source/metadata hashes are in
`.tmp/essd_revision_2026-09-23/release_preflight.json`.

## Approved commands

From the repository root:

```bash
pixi run --as-is python scripts/package_dataset.py \
    --amend-metadata-from release/CAMELS_RU_v1.0 \
    --output-dir release/CAMELS_RU_v1.1
pixi run --as-is python scripts/verify_release_revision.py \
    --source-dir release/CAMELS_RU_v1.0 \
    --revised-dir release/CAMELS_RU_v1.1
pixi run --as-is python scripts/verify_macros.py \
    --release-dir release/CAMELS_RU_v1.1
```

The approval also covered an isolated IOOS Compliance Checker 6.1.0 installation
and CF-1.8 checks on all three copied NetCDFs. Keep the installation, caches and reports under
project `.tmp/`; do not modify `pyproject.toml` or `pixi.lock`. Record the resolved
checker environment. Use the documented command-line interface:

```bash
compliance-checker --version
for product in discharge forcing water_level; do
    compliance-checker --test=cf:1.8 --criteria=strict --format=json \
        --output=".tmp/essd_revision_2026-09-23/cf_${product}.json" \
        "release/CAMELS_RU_v1.1/camels_ru_${product}.nc" || exit 1
done
```

Checker reference: <https://pypi.org/project/compliance-checker/6.1.0/> and
<https://github.com/ioos/compliance-checker>. No CF pass is claimed yet. If checking
finds further required changes outside the enumerated amendment, report them before
changing the candidate; do not alter scientific values or suppress checks to pass.

## Evidence already available

- Synthetic three-NetCDF amendment with the full 3353-ID mapping and packed/missing
  values; rejection tests for changed data, signed zero, invalid joins, overwritten
  output paths, omitted provenance and substituted documentation.
- Exact 19-signature and 288-attribute metadata coverage; 11 excluded categorical
  means and qualified interpretation of upstream/point/total fields.
- Independent spec and code reviews; demonstrated findings corrected and rechecked.
- Original release checksum verification and the real-data read-only preflight.

The candidate will still require author review, complete compliance/equivalence
evidence, actual archival identifiers, anonymous access and uploaded-file parity.
Licensing, authorship, historical AI use and immutable final provenance remain
separate submission gates.
