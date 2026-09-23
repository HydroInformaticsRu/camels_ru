# Approved CF-1.9 correction — 23 September 2026

## Outcome and scope

The user approved the concrete follow-up in `CF_VALIDATION_2026-09-23.md`.
The preferred local candidate is `release/CAMELS_RU_v1.1_cf19/`, built directly
from frozen v1.0. All three real NetCDF files pass strict CF-1.9 checks with IOOS
Compliance Checker 6.1.0. No checker patch, skipped check or suppressed exception
was used. This is a local validation result, not a publication or author approval.

Both `CAMELS_RU_v1.0` and the first `CAMELS_RU_v1.1` candidate remain untouched.
The latter's failed CF-1.8 reports and diagnosis are retained, not overwritten.
The directory suffix identifies this local schema candidate; `dataset_version`
remains 1.1, with no new DOI or claim that it has been archived.

## Exact amendment

- Rename only the instance dimension from `gauge_id` to `station`, retaining
  `gauge_id(station)` strings and their original order.
- Declare CF-1.9; retain int64 time and add `standard_name="time"`, `long_name="Time"`.
- Add authoritative station `lat(station)` / `lon(station)` and explicitly associate
  `gauge_id lat lon` with station data variables. Forcing remains basin-averaged.
- Include the existing 19-variable signature crosswalk and 288-variable attribute
  metadata, with separate CF19 README/changelog sources and amendment provenance.
- Select the exact verifier contract through `schema_revision="cf19_station"`;
  unknown revisions fail. Legacy candidate verification remains supported.

Full comparisons verify original raw and decoded values, missingness, IDs, order,
types, packing, filters and chunks, permitting only the documented dimension-name
mapping and metadata changes. All eight existing CSV/GeoPackage files are byte
identical. No signatures, grading thresholds, strict Grade-A rule, interpolation,
observations, flags, boundaries or attribute values were recalculated.

The shared reader `src/utils/release_io.py` validates the station identifiers,
returns a gauge-indexed view with `swap_dims`, and retains file-close semantics.
Sixteen script consumers and `examples/load_camels_ru.py` use it. Actual-schema
audits and repair writers retain raw opens. Default analysis paths remain v1.0.

## Verification

| File | Strict CF-1.9 score | Process exit | Reported findings |
|---|---:|---:|---:|
| discharge | 215/215 | 0 | 0 |
| forcing | 373/373 | 0 | 0 |
| water level | 265/265 | 0 | 0 |

All JSON results and stderr logs are retained together. The checker environment
is recorded in `evidence_2026-09-23/cf_checker_environment.json` (117 packages).
No project dependency manifest was modified.

- Complete independent equivalence checks pass for both amendment candidates.
- Exhaustive manifest checks pass: v1.0 has 12 entries; each candidate has 16.
- The preferred candidate passes 398 numerical macro checks, with no drift or
  skipped evidence. These check numerical agreement, not independent scientific truth.
- All 18 `tests/test_*.py` scripts pass, including both schema variants, packed
  synthetic arrays/masks, malformed identifier handling and provenance attacks.
- Src lint, scoped Ruff across changed Python, configured typecheck and whitespace
  checks pass. The typecheck is the repository's smoke configuration.
- Loading examples for v1.0 and CF19 return identical summaries: 2170 observed
  discharge gauges, 936 Grade A, median mean daily runoff 0.83 mm/day, 3339
  attribute rows and 277 retained qualified value fields.
- Final LaTeX build: 52 pages, no undefined references/citations, overfull boxes or
  oversized floats. All ten figures precede Data availability (page 47). Updated
  schema text and the relocated figure pair were visually inspected; correspondence
  renders. The PDF is `.tmp/essd_revision_2026-09-23/build/main.pdf`.
- Independent read-only code review found no concrete regression or blocker;
  its packaging and reader regression runs passed.

The source and first-candidate manifest SHA-256 hashes remain, respectively:

```text
947bb60d6b6e70605037fb72712d8bac7387bb16b37b317b6864a48cb22c1c7e
84c66d60281ecac55924db75aa2ba25b6006ad1d44a10f736543ef2665305a42
```

The preferred candidate's manifest SHA-256 is:

```text
c6b763e4a3b7f9f526eb6d03acc6619e2ef8ddc7ee79e323f18a6cd10ed30e3e
```

## Commands

Executed from the repository root. The build command intentionally refuses an
existing destination; it documents this completed build and must not be rerun
against the existing candidate.

```bash
pixi run --as-is python scripts/package_dataset.py --amend-metadata-from release/CAMELS_RU_v1.0 --output-dir release/CAMELS_RU_v1.1_cf19 --cf19
pixi run --as-is python scripts/verify_release_revision.py --source-dir release/CAMELS_RU_v1.0 --revised-dir release/CAMELS_RU_v1.1_cf19
pixi run --as-is python scripts/verify_release_revision.py --source-dir release/CAMELS_RU_v1.0 --revised-dir release/CAMELS_RU_v1.1
pixi run --as-is python scripts/verify_macros.py --release-dir release/CAMELS_RU_v1.1_cf19
pixi run --as-is python examples/load_camels_ru.py release/CAMELS_RU_v1.1_cf19
pixi run --as-is python examples/load_camels_ru.py release/CAMELS_RU_v1.0
for t in tests/test_*.py; do pixi run --as-is python "$t" || exit; done
pixi run --as-is lint
pixi run --as-is typecheck
```

The checker was invoked independently for each file, retaining process exit codes:

```bash
for name in discharge forcing water_level; do
  TMPDIR="$PWD/.tmp/essd_revision_2026-09-23/tmp" \
  XDG_CACHE_HOME="$PWD/.tmp/essd_cf_checker/xdg" \
  "$PWD/.tmp/essd_cf_checker/cache/cached-envs-v0/d0e019384e8a72d6/bin/compliance-checker" \
    --test=cf:1.9 --criteria=strict --format=json \
    --output=".tmp/essd_revision_2026-09-23/cf19_${name}.json" \
    "release/CAMELS_RU_v1.1_cf19/camels_ru_${name}.nc" \
    > ".tmp/essd_revision_2026-09-23/cf19_${name}.log" 2>&1
  test "$?" -eq 0 || exit 1
done
```

## Evidence and remaining gates

Fresh reports live under `.tmp/essd_revision_2026-09-23/`; durable copies are under
`paper/reviews/evidence_2026-09-23/`. `cf19_build_verification.json` binds this
follow-up to its logs and candidate manifest. The frozen original review and plan
are preserved; the current revision log links both failed and successful checks.

Final manuscript approval, final author list/order and contributions, source-data
redistribution/licensing evidence, accurate historical AI-use disclosure, immutable
final code/manuscript/release provenance, anonymous access and uploaded-file parity
remain author/external gates. Neither candidate was uploaded. No commit, push,
submission, notebook execution or full data pipeline was performed.
