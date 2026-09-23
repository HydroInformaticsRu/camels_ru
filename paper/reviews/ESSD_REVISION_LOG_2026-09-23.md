# ESSD revision log — 23 September 2026

## Authorisation and baseline

The user approved a separately versioned correction before submission and then
instructed: "Implement the plan." Local implementation is authorised. This does not
certify co-author approval, redistribution rights, compliance, access, provenance or
AI-use history. Initially no commit, push, upload or submission was authorised.
After reviewing the completed local revision, the user explicitly authorised
committing both repositories. Push, upload and submission remain unauthorised.
The user subsequently approved the concrete release build and isolated checker.
The v1.1 build and full numerical comparison pass; strict CF-1.8 validation fails.
The user then approved the separate CF-1.9 schema correction. Its build and all
three strict CF-1.9 checks pass; see `CF19_VALIDATION_2026-09-23.md`.

Parent baseline: e1ec631a3e36816b3016f6222a0070e442cf5b76 (main).
Manuscript baseline: 0c2185a786c13e203a83cbbf40da731e43a907fd (master).
Both worktrees were clean at implementation start. Remote freshness is unverified.

Approved local plan: docs/ESSD_REVISION_PLAN_2026-09-23.md (ignored by git).
Original review: docs/ESSD_READINESS_REVIEW_2026-09-23.md (ignored, unchanged).
Archived review: paper/reviews/ESSD_READINESS_REVIEW_2026-09-23.md.
Review SHA-256: 08e649c83a21feaf66df9cc083bb594a97bee744cf04e6c75f9ef4ae9be4b1a9.
Baseline evidence: .tmp/essd_review_2026-09-23/ (retained).
Revision evidence: .tmp/essd_revision_2026-09-23/.

The federation-advisor executable is absent. Bounded local agent work and
independent read-only review are used; their findings require source verification.

## Findings and dispositions

| ID | Original issue | Approved local correction | State / evidence |
|---|---|---|---|
| R1 | Runoff and nested-volume screens described as physical proof | Conditional diagnostics; retain estimands and thresholds | Implemented locally; author review remains required |
| R2 | Unqualified CAMELS interoperability | 19-variable crosswalk; no silent harmonisation | Implemented locally; author review remains required |
| R3 | Averaged categorical HydroATLAS codes | Preserve values, exclude 11 codes from categorical use; document spatial support | Implemented locally; author review remains required |
| R4 | Unsupported CF-1.8 statement | Safe coordinate/metadata amendment; complete equivalence and compliance checks | Preferred CF-1.9 candidate built; complete equivalence, 398 macro checks and all three strict CF-1.9 checks pass; earlier failure preserved |
| R5 | Boundary, flag, artefact and observation contradictions | Correct scope/count/provenance against source | Implemented locally; author review remains required |
| R6 | Dependent-gauge inference and causal explanations | Descriptive medians/IQR; qualify hypotheses | Implemented locally; author review remains required |
| R7 | Figure information encoding | Correct flow arrows, classes, counts, dates and captions without redesign | Implemented locally; author review remains required |
| R8 | Submission assertions without confirmations | Accurate pending gates and reviewable draft, no fabricated approvals | Open author/external gates |

## Author and external submission gates

- Final scientific wording and complete manuscript approval by all authors: unresolved.
- Source-data redistribution and licensing basis for all products: unresolved.
- Final author list/order, contributions, affiliations and disclosures: unresolved.
- Accurate historical AI-use disclosure under current ESSD policy: unresolved.
- Concrete revised-release generation and isolated checker installation: approved and executed.
- Local CF checker gate: closed for the approved CF-1.9 candidate; all three strict checks pass.
- Immutable final code/manuscript/release/environment provenance: unresolved.
- Anonymous repository access, actual v1.1 identifier and uploaded-file parity: unresolved.

This is an AI-assisted local revision for author review, not evidence of policy
compliance or submission readiness. All scientific edits must be reviewed by the
authors; the previous claim that no text or interpretation was machine-generated
must not be treated as verified.

## Verification

Initial revision checks completed (CF-1.9 follow-up verification is recorded below):

- LaTeX build: 52 pages. No undefined references/citations, overfull boxes or
  oversized floats. Correspondence renders. All ten figures occur on pages
  5, 8, 16, 35, 36, 38, 43, 44, 45 and 46, before Data availability on page 47.
- All ten asset pairs are byte-identical across the two image directories. Nine
  figures were regenerated; the quality-map asset was retained. Rendered figure
  pages, the new descriptive table and the HydroATLAS table were visually inspected.
- `pixi run --as-is python scripts/verify_macros.py --release-dir release/CAMELS_RU_v1.0`:
  398 checks passed, no drift or skipped evidence. This remains a check of released
  values plus retained audit artifacts, not independent truth of all claims.
- All 17 `tests/test_*.py` scripts passed. Release/provenance and release-selection
  checks were rerun after their final logic changes. Test-first regression evidence
  is retained for coordinate amendments, plot classes and release selection.
- `pixi run --as-is lint`, scoped Ruff across changed Python, both diff-whitespace
  checks and `pixi run --as-is typecheck` pass. Typecheck is the configured smoke
  check, not a claim of exhaustive semantic typing.
- Every one of the 12 frozen v1.0 manifest entries passes SHA-256 verification.
  Original/archived readiness-review bytes match their recorded hash.
- Actual source preflight passes metadata coverage and all 3353 station joins for
  each of the three released NetCDFs. The complete candidate equivalence test was
  subsequently run on the actual generated v1.1 bundle and passed. Both manifests
  pass, and the v1.1 macro verifier reports 398 successful checks. Strict CF-1.8
  checking did not pass; its JSON reports and exception logs are retained.

Logs, rendered pages and machine-readable summary:
`.tmp/essd_revision_2026-09-23/`, particularly `final_verification.json`,
`verify_macros_final_v1.0.log`, `typecheck_fixed.log`, and `build/main.pdf`.
Selected durable evidence is copied to `paper/reviews/evidence_2026-09-23/`.
The concrete gated action is documented in
`paper/reviews/RELEASE_AMENDMENT_APPROVAL_2026-09-23.md`.

The separately approved metadata-only v1.1 build was performed. No notebooks,
full data pipelines, external publication, commits or pushes were performed.
Project dependency manifests are unchanged; checker dependencies are isolated
under project `.tmp/essd_cf_checker/`.


## Evidence-based refinements to the approved plan

The original review and archived plan are retained without retroactive corrections.
Implementation followed current source/release evidence where that evidence refined
an earlier description:

1. **Event durations and flashiness.** The review's event-gap statement was stale:
   `FlowExtremes._calculate_event_durations` already splits at missing calendar days
   (commit 5d12394 and `tests/test_event_durations.py`). BFI and flashiness still
   collapse gaps; flashiness additionally excludes the first retained value from
   its denominator. A bounded read-only audit reproduced both durations and
   flashiness for all 1729 released rows at CSV precision. Manuscript/crosswalk now
   document these actual definitions; no signature values were changed. See
   `evidence_2026-09-23/audit_signature_dates.py` and `.log`.
2. **HydroATLAS source units.** Local `data/World/docs/BasinATLAS_Catalog_v10.pdf`,
   pp. 56–57, identifies `gdp_ud_sav` as GDP per capita (2011 international USD),
   not density, and `hdi_ix_sav` as an index stored x1000. The latter is not rescaled
   by the extractor. Descriptions and metadata now reflect this; values are intact.
3. **Grade-selection summaries.** Added a compact table with medians, quartiles and
   finite sample sizes, verified by 30 additional macros. Winter-flow medians are
   0.27 for strict A versus 0.54 for other graded gauges; text states the correct
   direction. Half-flow and winter-flow sample counts are variable-specific.
4. **Comparator scope.** CAMELS-US quantile orientation is supported by Addor2017.
   No universal Caravan signature counterpart was verified; the crosswalk says so
   explicitly and the manuscript no longer claims such a verified equivalence.
5. **Typecheck environment.** The original smoke command failed to discover Pixi
   site-packages (107 missing-import errors). Verbose diagnostics isolated search
   path configuration; adding `venvPath: .pixi/envs` and `venv: default` to
   `pyright.smoke.json` restores the task (0 errors/warnings), without disabling
   rules or adding dependencies.
6. **Layout and legibility.** Wrapped the nested-results path using `\path`, reduced
   appendix image height from 0.85 to 0.82 textheight for the longer caption, and
   raised the newly added precipitation/cold-region count labels to remain readable
   at manuscript size. All ten figures remain.

## Independent review and fixes

An independent spec/scientific-consistency review checked the manuscript and all
19/288 metadata entries. Its comparator, interpolation wording, descriptive spread,
causal wording, candidate-status and ERA5-label findings were corrected. A follow-up
caught the direction of the winter-flow contrast; the release values and rendered
text now agree. The conditional interpretation also extends to the forcing table
and known-artefact descriptions.

A separate code review demonstrated that omitted provenance could bypass document
checks in the first amendment verifier. The existing regression test now reproduces
and rejects that attack, including missing/malformed metadata/code records,
inconsistent dirty flags and substituted README/CHANGELOG content. The reviewer
rechecked the fix. Code provenance records uncommitted state truthfully; it does not
assert that dirty code is contained in the recorded baseline commit.

These local reviews do not constitute author approval or predict journal acceptance.


## Approved build and CF result

The v1.1 candidate is now at `release/CAMELS_RU_v1.1/`. The original v1.0 was not
modified. Full numerical/layout/packing comparisons and both checksum manifests
pass; 398 manuscript numerical checks also pass against the candidate.

IOOS Compliance Checker 6.1.0 was installed in the approved isolated environment
(117 resolved packages recorded). All three strict CF-1.8 checks exit 2: inherited
int64 time is unsupported by that convention, time lacks name metadata expected
by the checker, and the checker raises an exception on `gauge_id(gauge_id)` strings.
No failing checks were hidden. The detailed diagnosis and an approval-gated CF-1.9
follow-up are in `CF_VALIDATION_2026-09-23.md`; a synthetic schema test is explicitly
separate from the real candidate and supplies no real-release conformance verdict.

The candidate's data and schema have not been changed after the CF result. The
manuscript and status documents now state that the local build exists and that CF
validation remains unresolved. No new archive identifier or author agreement was
fabricated.


## Approved CF-1.9 correction and final local verification

The user approved the concrete follow-up described in `CF_VALIDATION_2026-09-23.md`.
A separate `release/CAMELS_RU_v1.1_cf19/` candidate was built directly from v1.0.
Only the approved instance-dimension rename, time metadata, convention declaration,
identifier associations and coordinate/sidecar additions are allowed by the verifier.
The earlier v1.0 and first v1.1 packages are unchanged, including manifest bytes.

All three real NetCDFs pass strict CF-1.9 checks with IOOS Compliance Checker 6.1.0;
no checker patch, skip or suppressed exception was used. Complete comparisons pass
for both candidates against v1.0, preserving raw/decoded values, missingness, IDs,
ordering, dtypes, packing and existing CSV/GeoPackage bytes. Candidate numerical
verification passes 398 checks. All 18 test scripts, scoped Ruff, src lint and the
configured typecheck pass. Both schema loading examples return identical summaries.
Independent read-only code review found no concrete blocker; its bounded regression
checks passed. Final manuscript wording identifies the checked local schema without
claiming publication or source licensing confirmation. The rebuilt PDF is checked
separately in the follow-up report.

Reader normalization lives in `src/utils/release_io.py`; 16 read-only script consumers
and the loading example use it. Raw-schema audits and repair writers remain raw;
no analysis pipeline or notebook was executed. The frozen review and plan are intact.
See `CF19_VALIDATION_2026-09-23.md` for exact commands, report scores, hashes and
remaining author/external gates. This closes local CF checking, not submission gates.


## Authorised local commit checkpoint

The user explicitly authorised commits in both repositories after the successful
CF-1.9 revision. The manuscript is committed first and the parent repository records
that exact gitlink together with the implementation, metadata and review trail.
The manuscript code-availability wording no longer describes the revision as
uncommitted; final archival identification remains an external submission gate.
Release directories and their build-time provenance remain untouched. Their recorded
dirty build state remains historically correct; commits do not retrospectively
change the inputs from which the candidates were generated.

No push, upload or submission is included in this authorisation. Local commit IDs
are reported separately after creation; remote freshness remains unverified.

Manuscript commit: `d6c45acc6b51ff2943ceb1fc6166827021c01210`. The parent commit containing this log records that
exact gitlink. Fresh release/evidence integrity checks and the 52-page PDF build
passed; `evidence_2026-09-23/commit_checkpoint.json` records the checkpoint.
