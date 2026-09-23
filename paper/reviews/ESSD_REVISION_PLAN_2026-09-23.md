# CAMELS-RU ESSD revision plan

Approved for local implementation by the user on 23 September 2026. This is the
execution record of the plan presented in the planning session. External submission
gates and the separate approval of the concrete release amendment remain open.

## Scope, baseline, and review trail

Outcome: an author-approved ESSD data descriptor supported by a separately versioned
v1.1 release, required before submission. Preserve v1.0 unchanged. Retain existing
signature definitions, grading thresholds, strict Grade A, and the useful figure
design. Defer harmonised signature calculations, new inferential analyses, and
additional figures. Publication costs and journal selection are settled.

Verified baseline: parent main e1ec631a3e36816b3016f6222a0070e442cf5b76;
manuscript master 0c2185a786c13e203a83cbbf40da731e43a907fd. Both clean and matching
their locally recorded remote refs. Remote freshness not established. Baseline
build and numerical checks establish reproducibility, not submission readiness.

Preserve docs/ESSD_READINESS_REVIEW_2026-09-23.md and
.tmp/essd_review_2026-09-23/ unchanged. Review SHA-256:
08e649c83a21feaf66df9cc083bb594a97bee744cf04e6c75f9ef4ae9be4b1a9.

Create an unchanged archival copy at
paper/reviews/ESSD_READINESS_REVIEW_2026-09-23.md and a findings/decisions/evidence
ledger at paper/reviews/ESSD_REVISION_LOG_2026-09-23.md. Use
.tmp/essd_revision_2026-09-23/ for new evidence. Preserve unresolved findings.
The ignored original and this local plan alone are not immutable public provenance.

## Prioritised local tasks

### P1 — Interpretation and factual corrections

Affected manuscript sections under paper/overleaf/sections/: 00_abstract.tex,
01_introduction.tex, 05_attributes.tex, 06_data_records.tex, 07_validation.tex,
08_example_application.tex, 09_limitations.tex, 10_conclusions.tex.
Supporting files: paper/overleaf/tables/hydro_signatures.tex,
paper/overleaf/tables/nested_stratification.tex, scripts/nested_mass_balance.py,
scripts/create_paper_signatures.py.

- Describe runoff-ratio exceedances as conditional screening results. State paired
  days, annual aggregation, incomplete seasonal coverage, and unresolved storage,
  transfer, forcing, area and observation uncertainty. Do not claim annual averaging
  caused false positives: the review found all 105 screened non-anomalous gauges
  also exceeded one using pooled paired-day totals.
- Describe geometric nesting/volume ordering. Point containment does not prove river
  connectivity; coincident reporting dates do not eliminate routing, storage,
  sampling, withdrawal or loss effects. Remove universal downstream-volume guarantees
  and "noise cannot explain". Retain area stratification and pair dependence.
- Replace population significance claims with medians, spread and sample sizes;
  remove individual-gauge bootstrap intervals from the cold-region demonstration.
- Qualify snow-cover, precipitation-phase, ice-window and filter-timescale
  explanations. Retain the warning that filtered BFI is not measured groundwater.
- Describe A–F as reproducible screening/consistency grades. Preserve thresholds.
- Correct 3353 visual boundary checks versus 3011 reference-area comparisons and
  342 without reference; 1798 nested-screen gauges versus 2106 stage–discharge;
  unflagged nested failures; eight existing artefact entries rather than seven;
  available discharge includes 1691 interpolated gauge-days; 21 defined flags versus
  16 active in default grading.
- Correct matching generator comments/docstrings/messages/captions without changing
  calculations. Every scientific correction gets a review-log entry and author review.

### P2 — Interoperability and attribute metadata

Create paper/metadata/signature_crosswalk.json,
paper/metadata/hydroatlas_metadata.json, paper/metadata/README_v1.1.md,
paper/metadata/CHANGELOG_v1.1.md. Update relevant sections/tables above plus
paper/overleaf/tables/hydroatlas_attributes.tex, README.md,
examples/load_camels_ru.py, and directly affected AGENTS_REFERENCE.md entries.

Crosswalk: all 16 signatures and three ERA5 variants. Each records units, definition,
aggregation, eligibility, missing-date handling, interpolation policy, comparator
variable, comparator source/version and equivalence limitations. Distinguish
exceedance/non-exceedance quantiles, annual/whole-record statistics, 2x/9x median
thresholds, percent/days-per-year frequencies and collapsed missing-date gaps.
Swapping names or units is not complete harmonisation. Use CAMELS framework/family.

Attribute metadata covers 281 HydroATLAS fields plus seven derived fields. Preserve
legacy values but mark these eleven averaged codes unusable as category identifiers
and exclude them from recommended analysis: clz_cl_smj, cls_cl_smj, glc_cl_smj,
pnv_cl_smj, wet_cl_smj, tbi_cl_smj, tec_cl_smj, fmh_cl_smj, fec_cl_smj, lit_cl_smj,
gad_id_smj. Do not round them or claim modal replacements. Audit source spatial
support (upstream, sub-basin, point), document averaging, and qualify interpretation
without silently replacing upstream aggregates or declaring all such fields wrong.

### P3 — Separately approved v1.1 amendment

Modify scripts/package_dataset.py. Create scripts/verify_release_revision.py and
tests/test_release_metadata.py. Add:

    --amend-metadata-from SOURCE_DIRECTORY --output-dir NEW_DIRECTORY

SOURCE_DIRECTORY and NEW_DIRECTORY describe the interface, not runnable commands.
The executable command below uses resolved paths. Verify the source manifest,
refuse overlapping source/output or an existing destination, copy before amendment,
and bypass parsing, grading, filling, signatures and attribute extraction.

Add lat(gauge_id), lon(gauge_id) to all three NetCDFs from
data/CAMELS_RU/geometry/camels_gauges.gpkg. Join unique string IDs; validate explicit
CRS, point geometry, finite ranges and complete matches. Use station coordinates,
not centroids; forcing remains basin-averaged. Reuse the coordinate-writing helper
in normal packaging. Associate data with coordinate metadata. Coordinates alone do
not prove CF compliance: validate against CF-1.8, including manual review.

Candidate files include signature_crosswalk.json, hydroatlas_metadata.json, revised
README.md, CHANGELOG.md, REVISION_PROVENANCE.json and SHA256SUMS. Record source and
station checksums/CRS, actual amendment code provenance and permitted changes.
Never invent final hashes, DOI or approval. v1.0 bytes stay untouched; existing
NetCDF data, dimensions, ordering, missingness, flags and packing stay unchanged;
existing CSV/GPKG payloads remain byte-identical. Enumerate metadata changes.
Failed compliance must not trigger unapproved numerical changes. v1.1 is the intended
submission dataset, v1.0 its frozen numerical baseline.

### P4 — Figure repairs

All assets stay byte-identical in paper/images/ and paper/overleaf/images/.

| Figure | Source; caption under paper/overleaf/sections/ | Required repair |
|---|---|---|
| 1 | scripts/regenerate_gauge_network_figure.py; 02_study_area.tex | Sparse labelled orientation, climate abbreviations; preserve classes/design |
| 2 | paper/figures_src/fig_workflow.tex; 03_data_sources.tex | Discharge/forcing/area inputs to signatures, accurate aggregation arrows, discharge-only grading, reservoir-stage 15-day exception |
| 3 | 04_time_series.tex | Accurate screening caption; retain asset unless changed |
| 4 | scripts/regenerate_precip_comparison_figure.py; 07_validation.tex | Unequal classes and open tails; differences not measured errors |
| 5 | scripts/generate_budyko_figure.py; 07_validation.tex | Conditional envelope; per-axis and distinct off-axis counts |
| 6 | scripts/plot_coldregion_gradient.py; 08_example_application.tex | Hydro-year dates, linear temperature scale, all-bin finite counts, medians/IQR without bootstrap inference, off-axis counts |
| B1–B4 | src/plots/paper_maps.py and scripts/plot_signature_maps.py; appendix_tables.tex | Open outer classes, numeric histogram counts, quantile orientation, finite/missing counts, grey-missing caption |

Keep boundaries/colours; make map and histogram membership identical. Precipitation
has its own colourbar. B4 source already requests letters: inspect regenerated
output before adding logic. Add tests/test_paper_figure_encoding.py for class edges,
tails, empty/missing classes, totals and finite bin counts, including roundoff just
above 100%. Expected populations: 1716 signature gauges; 1641 half-flow dates/75
missing; 1117 cold-region gauges/57 beyond the winter-ratio display limit.

### P5 — Reconcile and verify

Update scripts/verify_macros.py, scripts/coldregion_robustness.py,
paper/overleaf/macros.tex, paper/overleaf/main.tex, paper/overleaf/refs.bib,
paper/overleaf/tables/dataset_files.tex, paper/overleaf/tables/timeseries_variables.tex,
paper/README.md and directly affected AGENTS_REFERENCE.md entries.
Add --release-dir to the macro verifier and pass through the cold-region loader.
Remove the Mann–Whitney gate, retain descriptive checks. Keep figure calculations
on the documented v1.0 baseline and prove v1.1 applicability by content equivalence.
Record external inputs/table changes. Streamline repeated caveats without deleting
methods, qualifications or figures. No supplement restructuring is required.

## Verification commands

Run only after implementation and the relevant release/dependency approvals.

```bash
pixi run --as-is lint
pixi run --as-is typecheck
for t in tests/test_*.py; do
    pixi run --as-is python "$t" || exit 1
done
git diff --check
git -C paper/overleaf diff --check

pixi run --as-is python scripts/package_dataset.py --amend-metadata-from release/CAMELS_RU_v1.0 --output-dir release/CAMELS_RU_v1.1
pixi run --as-is python scripts/verify_release_revision.py --source-dir release/CAMELS_RU_v1.0 --revised-dir release/CAMELS_RU_v1.1
(cd release/CAMELS_RU_v1.0 && sha256sum -c SHA256SUMS)
(cd release/CAMELS_RU_v1.1 && sha256sum -c SHA256SUMS)
pixi run --as-is python scripts/verify_macros.py --release-dir release/CAMELS_RU_v1.0
pixi run --as-is python scripts/verify_macros.py --release-dir release/CAMELS_RU_v1.1
```

After approval, use isolated IOOS Compliance Checker 6.1.0 without changing project
dependencies; record the environment and reports. Check each NetCDF with
`compliance-checker --test=cf:1.8 --criteria=strict --format=json`, with output under
.tmp/essd_revision_2026-09-23/ and each candidate file as input. Full-content
equivalence is mandatory; summary agreement is insufficient.

```bash
pixi run --as-is python scripts/regenerate_gauge_network_figure.py --write
pixi run --as-is python scripts/regenerate_precip_comparison_figure.py --write
pixi run --as-is python scripts/generate_budyko_figure.py
pixi run --as-is python scripts/plot_coldregion_gradient.py
pixi run --as-is python scripts/plot_signature_maps.py --write
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=paper/figures_src paper/figures_src/fig_workflow.tex
cp -p paper/figures_src/fig_workflow.pdf paper/images/fig_workflow.pdf
cp -p paper/figures_src/fig_workflow.pdf paper/overleaf/images/fig_workflow.pdf
mkdir -p .tmp/essd_revision_2026-09-23/build
(cd paper/overleaf && latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=../../.tmp/essd_revision_2026-09-23/build main.tex)
pdftotext -layout .tmp/essd_revision_2026-09-23/build/main.pdf .tmp/essd_revision_2026-09-23/build/main.txt
```

Check mounted inputs and cached basemaps first. Inspect changes to
paper/tables/precip_comparison_caption.csv, paper/tables/forcing_water_balance.csv,
results/hess_quality/coldregion_gradient_bins.csv. Some preview commands overwrite
tables. Never use scripts/regenerate_paper_maps.py (executes notebooks).
Require no undefined citations/references, oversized floats or overfull boxes;
check correspondence, complete table rows and all figures before Data availability.
Inspect every rendered figure. Suppressed underfull reporting proves nothing.

## Author decisions and external gates

- Scientific framing: authors confirm conditional diagnostics and scientific wording.
- Statistical scope: descriptive comparisons; no new dependence-aware inference.
- Categorical fields: retain legacy means but exclude them as category identifiers.
- Release: separate approval of the concrete amendment, new schema/sidecars, v1.1
  generation and isolated checker installation before producing the revised release.
- Redistribution: evidence of source rights/permissions/public-data status for
  observations and redistributed products; public access alone does not settle this.
- Authorship: author list/order, affiliations, contributions, disclosures and agreement
  to the exact final version. No fabricated agreement.
- AI: reconcile actual history/tools with ESSD policy; do not assert no generated
  text/interpretation without evidence. Disclosure alone does not cure prohibited use.
- Provenance: freeze approved code, manuscript, environment, review trail and
  manifests; replace acceptance-time tag promise with actual immutable references.
  Commits, pushes, uploads and submission require separate authorisation.
- Access/parity: anonymous review access, every uploaded file downloaded and checked
  against approved manifest, actual citation/version identifiers and publication DOI.

Policy sources checked 23 September 2026:
https://www.earth-system-science-data.net/policies/data_policy.html
https://www.earth-system-science-data.net/policies/obligations_for_authors.html
https://www.earth-system-science-data.net/policies/ai_policy.html
https://cfconventions.org/Data/cf-conventions/cf-conventions-1.8/cf-conventions.html
https://github.com/ioos/compliance-checker
https://pypi.org/project/compliance-checker/6.1.0/

## Final review checklist

- [ ] Every review finding resolved or explicitly dispositioned by authors.
- [ ] Claims match implemented estimands and evidence.
- [ ] Strict Grade A, thresholds, periods, masks and numerical release preserved.
- [ ] Crosswalk/attribute metadata complete and qualified.
- [ ] Original checksums and candidate content-equivalence/CF reports pass review.
- [ ] Ten figure pairs match and counts/tails/missingness/dates/captions reconcile.
- [ ] Build, numerical verification, code checks and rendered inspection pass.
- [ ] Independent scientific/code review findings verified and resolved.
- [ ] Licensing/authorship/AI/provenance/access/parity gates closed.
- [ ] Authors approve the exact manuscript/release combination for submission.
