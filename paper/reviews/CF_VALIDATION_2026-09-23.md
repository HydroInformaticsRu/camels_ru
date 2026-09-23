# v1.1 build and CF validation — 23 September 2026

## Outcome

The user approved the concrete v1.1 build and isolated checker installation.
`release/CAMELS_RU_v1.1/` was generated locally. Complete source/candidate
comparison passes: original numerical values, missingness, identifiers, ordering,
types and packing are unchanged; the eight existing CSV/GeoPackage files are
byte-identical. All 12 source and 16 candidate manifest entries pass checksums.
The selected-release manuscript verifier reports 398 passing numerical checks.

**CF-1.8 validation did not pass.** None of the three NetCDFs has a completed passing
checker result. No findings were suppressed and the checker was not patched. The
candidate was not changed after the failed checks. Nothing was published or submitted.

## Checker and reports

IOOS Compliance Checker 6.1.0, isolated under `.tmp/essd_cf_checker/`, with 117 resolved
packages recorded in `evidence_2026-09-23/cf_checker_environment.json`. The project
`pyproject.toml` and `pixi.lock` are unchanged. Installation first failed because
sandbox networking was unavailable; the approved network escalation succeeded.

Command applied independently to each file: `compliance-checker --test=cf:1.8
--criteria=strict --format=json`. All three processes exited 2, reporting failed
checks and an exception. JSON and stderr logs are retained separately because the
JSON score does not turn an aborted check into a completed check.

| Candidate | Completed-check score (not a compliance verdict) | Findings |
|---|---|---|
| discharge | 198/202 | int64 time; missing time-name metadata; string-coordinate exception |
| forcing | 341/350 | Same findings, with the time-name check repeated for seven variables |
| water level | 247/251 | Same findings |

## Diagnosis

1. **Stored time type versus declared convention.** Every file has `time(time)` as
   int64, inherited unchanged from v1.0. CF-1.8 section 2.2 does not include int64
   among permitted types. CF-1.9 does, and the installed checker's CF1_9Check adds
   `np.int64` to the supported type set. Retargeting to 1.9 could retain all values
   and their storage types; converting time to int32 would violate the approved
   type-preservation contract.
2. **Time-name metadata.** All files have time units and a calendar, but no
   `standard_name` or `long_name`. The checker reports this under sections 3.3 and
   5.1. CF time identification through units is valid and `standard_name` is
   optional normatively; the checker is stricter here. Adding
   `standard_name="time"` and a descriptive `long_name` is an appropriate metadata
   improvement, not a correction to the dates.
3. **Same-name string identifier.** The files retain string `gauge_id(gauge_id)`.
   The checker's coordinate discovery uses dimension/name agreement and one
   dimension, with an explicit TODO for strings. Its monotonicity check applies
   `np.diff` and raises `unsupported operand type(s) for -: 'str' and 'str'`.
   This is a demonstrated checker exception, not by itself a standards verdict.
   Earlier CF/NUG definitions have a documented ambiguity; CF-1.12 explicitly
   prohibits this same-name one-dimensional string arrangement. Do not claim the
   earlier layout is unambiguously compliant merely by removing the exception.
4. **Identifier association.** Current data variables name `lat lon` in
   `coordinates`; a string identifier represented as an auxiliary label should
   also be explicitly associated as `gauge_id`.

Primary references:

- [CF-1.8 data types](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.8/cf-conventions.html#_data_types)
- [CF-1.9 data types](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.9/cf-conventions.html#_data_types)
- [CF-1.8 time coordinates](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.8/cf-conventions.html#time-coordinate)
- [CF string labels](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.8/cf-conventions.html#labels)
- [CF/NUG coordinate-definition discussion, issue 174](https://github.com/cf-convention/cf-conventions/issues/174)
- [CF-1.12 terminology](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.12/cf-conventions.html#terminology)

Installed implementation evidence: `compliance_checker/cf/cf_1_9.py:17–22`,
`cf/util.py:400–425`, and `cf/cf_1_6.py:559–575` in the recorded environment.

## Controlled probe and recommended follow-up

A two-station, two-day **synthetic** fixture isolates the identifier-layout issue.
Both variants declare CF-1.9, retain int64 time, provide its standard name, and
explicitly associate `gauge_id lat lon`. The variant with the dimension named
`gauge_id` still exits 2 with the same exception. The variant with dimension
`station` and string `gauge_id(station)` exits 0 with all applicable strict CF-1.9
checks passing. This is a schema feasibility result, not a pass for any real release.
The probe subprocess also emitted a PROJ database-path warning inherited from the
parent Pixi environment; the actual three release checks did not emit that warning.

Follow-up scope below was **approved by the user on 23 September 2026**.
The original failed candidate and its evidence remain unchanged. Real-file CF-1.9
results will be recorded separately after implementation and verification:

1. Target CF-1.9 while preserving all existing values, IDs, order and storage types.
2. Add time-name metadata and explicitly associate the identifier label.
3. Rename the instance dimension to `station`, keeping the identifier variable
   `gauge_id(station)` and data variables on `station × time`.
4. Update the release verifier to permit precisely that dimension-name mapping,
   and adapt readers/examples that currently assume `gauge_id` is a dimension.
   Xarray users can restore the prior labelled view with
   `ds.swap_dims({"station": "gauge_id"})`.
5. Build a separate candidate at `release/CAMELS_RU_v1.1_cf19/`, retaining both
   v1.0 and the inspected first v1.1 candidate. Repeat complete equivalence,
   numerical-macro and strict CF checks on all three real files; do not infer a
   full pass from the synthetic result.

This required explicit approval (now received) because it changes the convention declaration and
public dimension schema, exceeding the approved amendment's dimension-preservation
contract. The alternative of retaining the old schema would require resolving the
version-specific string-label ambiguity with a maintained validator; a skip flag
or silent checker modification is not an acceptable substitute.

## Evidence

Durable copies under `paper/reviews/evidence_2026-09-23/` include build and comparison
logs, both checksum logs, the v1.1 macro log, all three CF JSON/log pairs, the resolved
checker environment, and synthetic-probe source/results. Original outputs are under
`.tmp/essd_revision_2026-09-23/`.

Licensing evidence, final authorship/contributions, final AI-use disclosure,
immutable archival provenance, anonymous access and uploaded-file parity remain
unresolved submission gates. This report is not an author approval or acceptance
prediction.
