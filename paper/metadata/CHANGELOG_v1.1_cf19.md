# CAMELS-RU v1.1 — local CF-1.9 candidate

Status: prepared locally for review; not archived or published. No new DOI assigned.
The frozen `CAMELS_RU_v1.0` and inspected first `CAMELS_RU_v1.1` packages remain
unchanged. This candidate is built directly from v1.0 into `CAMELS_RU_v1.1_cf19`.

## Added

- Station latitude/longitude auxiliary coordinates and supporting coordinate metadata in
  the three candidate NetCDFs; compare with the authoritative station inventory using
  the amendment verifier.
- `signature_crosswalk.json`: code-grounded definitions for 16 signatures and three
  ERA5-Land variants, with source/version-specific comparisons and explicit limitations.
- `hydroatlas_metadata.json`: all 288 value fields (281 source plus seven derived),
  including conditional guidance for the primary 22 and exclusion of eleven categorical
  code means from the recommended analysis set.
- This changelog and a revised README documenting conditional diagnostics, interpolation
  provenance, signature differences and attribute support/units.

## Schema correction

- Declare CF-1.9, which permits the inherited int64 time storage type.
- Add `standard_name="time"` and `long_name="Time"` to the time coordinate.
- Rename only the instance dimension: `gauge_id` → `station`. Keep the string
  identifier variable as `gauge_id(station)` and all IDs/order unchanged.
- Associate `gauge_id lat lon` with station data variables. Readers can restore
  gauge-ID indexing using xarray `swap_dims({"station": "gauge_id"})`.
- Record `schema_revision="cf19_station"` in provenance and verify exactly this
  dimension-name mapping, with no relaxation of value/type/packing comparisons.

## Unchanged

Numerical discharge, stage and forcing arrays; existing interpolation/provenance flags;
quality flags and annual/overall grades; signature values, thresholds, eligibility and
screen columns; all attribute values; catchment polygons. Invalid categorical means
are retained for provenance, without rounding, reclassification or modal replacement.
Existing CSV/GeoPackage content is copied unchanged; NetCDF metadata changes require
array/flag identity checks, not byte identity of the NetCDF files. Manifest checksums
are regenerated for the candidate contents.

## Limits

No new harmonised signatures, categorical re-extraction or correction of upstream
aggregation is supplied. The GDP per-capita and stored HDI scale descriptions clarify
existing values. Station coordinates and a conventions string do not establish a
passed CF checker result: retain the separate validation status/report. Publication,
repository access, licence evidence and author agreement remain external gates.
