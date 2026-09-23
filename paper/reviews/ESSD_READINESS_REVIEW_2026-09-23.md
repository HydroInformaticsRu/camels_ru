# CAMELS-RU: internal ESSD readiness review

Reviewed 23 September 2026. This is an author-facing technical assessment, not a journal referee report or an acceptance prediction.

**Verdict: worthwhile ESSD contribution; substantial revision needed before submission.** Keep the data-descriptor framing and existing evidence. The highest priorities are scientific interpretation, interoperability, and accurate figure encoding. Starting the manuscript again or changing journals now would not resolve these issues.

## Scope and verified state

- Parent repository: `main`, `e1ec631`; nested manuscript: `master`, `0c2185a`. Both were clean at review start.
- Canonical source: `paper/overleaf/`. Reviewed the manuscript sections, relevant tables, all ten included figure assets, selected figure/data-processing code, and release metadata.
- Fresh LaTeX build succeeded: 51 pages. Final build log has no undefined-reference/citation warnings, overfull boxes, or oversized-float warnings. Underfull reporting is suppressed by the manuscript and is not a meaningful check. Correspondence renders; the ten figure captions precede Data availability.
- `sha256sum -c SHA256SUMS` passed for all 12 listed release files.
- `pixi run --as-is python scripts/verify_macros.py` passed: “No drift — all checked macros reproduce from release + audit artifacts.” It checks a mixture of release-derived values and retained audit tables, not independent truth of every scientific claim.
- All ten figure assets are byte-identical between `paper/images/` and `paper/overleaf/images/`.
- Checked counts include 3353 boundaries, 2170 discharge gauges, 2989 water-level gauges, 936 strict Grade-A gauges, 1716 non-anomalous signature gauges, and 188 weak stage–discharge records.
- Build, extracted text, figure previews, and macro-verification log are retained under `.tmp/essd_review_2026-09-23/`. No manuscript, source code, release files, or external records were changed. No notebooks or full data pipelines were run.

Scope limits: this is not a fresh verification of all 3353 boundaries, all source observations, every bibliographic claim, or a complete CF checker run. Zenodo public/review access could not be established from this environment: web access failed and direct requests returned connection errors. This does **not** establish that the review link is broken. The repository's federation-advisor executable is absent; two bounded read-only agent reviews supplemented the main review, and substantive findings below were checked against current sources/artifacts.

## Why the paper is worth finishing

The contribution is the combination of Russian observations, catchment geometry, forcing, attributes, and explicit screening/provenance. These are central ingredients of CAMELS-family datasets. The manuscript has a clear release/analysis/quality subset distinction, annual grades, imputation flags, documented failure cases, substantial sensitivity analyses, and useful release instructions. It correctly explains why the GRDC comparison verifies ingestion rather than independently validating Roshydromet observations.

ESSD evaluates dataset utility, access, processing quality, and presentation. It does not require this descriptor to establish a new causal explanation of permafrost hydrology. Published [CAMELS-GB](https://essd.copernicus.org/articles/12/2459/2020/) and [CAMELS-CH](https://essd.copernicus.org/articles/15/5755/2023/) are appropriate comparison points. They support the dataset family concept, not a universal requirement to use one forcing product or identical record length. The 16-year record is a limitation to state, not by itself a reason the dataset cannot be published.

## Scientific findings, in priority order

### 1. Correct the physical interpretation of the screening tests

`paper/overleaf/sections/07_validation.tex:47` interprets mean annual runoff ratios above one as a water balance that cannot close and assigns exclusive physical explanations. However, `05_attributes.tex:25` states that ratios use days carrying discharge, potentially omitting winter precipitation while retaining its spring runoff. Mean annual ratios also differ mathematically from a cumulative water balance.

A bounded release check found that all 105 non-anomalous screened gauges also exceed one using pooled paired-day totals over the same eligible years. Therefore **annual-ratio averaging was not demonstrated to cause false positives in this release**. Nevertheless, 36 of these gauges have less than 95% discharge coverage over the fifteen years, and storage, forcing, area, and observation uncertainty remain unresolved. Describe the screen as a potential inconsistency under stated assumptions. A stronger physical claim requires a sufficiently complete, common-period cumulative balance and explicit storage/import assumptions.

`07_validation.tex:9` likewise says downstream volume must exceed upstream volume on any jointly observed period. Routing delay, storage changes, disconnected sampling dates, withdrawals, and natural losses prevent that guarantee. The text itself acknowledges losses at line 17. A point lying inside another watershed is also weaker evidence than verified river connectivity and watershed containment. Retain the check as a volume-ordering diagnostic; remove the claim that area ratio alone rules out noise (line 15). Emphasise the comparable-area stratum alongside the 99.3% overall pass rate.

### 2. Repair or qualify CAMELS interoperability

`05_attributes.tex:34` explicitly documents reversed `q05`/`q95` meanings relative to CAMELS-US/Caravan, annual rather than whole-record thresholds, and a high-flow threshold of twice rather than nine times the median. Lines 27–31 document collapsing missing-date gaps in filtering, flashiness, and event durations. These are substantive definition differences; converting percentages to days/year is not enough to harmonise them.

Recommend a clearly named, harmonised signature product for cross-CAMELS use, preserving traceability to the existing definitions. At minimum, provide a machine-readable variable crosswalk and prominently distinguish non-equivalent signatures. Use “CAMELS framework/family” rather than an unqualified “CAMELS standard” or an assurance of effortless merging. CAMELS-family eligibility and exact variable interchangeability are different questions.

The attribute section also acknowledges averaging categorical class codes (`05_attributes.tex:5`). Fractional codes are not meaningful categories. Correct these to an appropriate categorical aggregation, or explicitly remove them from the recommended usable feature set and document the limitation in machine-readable metadata. Audit the spatial meaning of averaging upstream-aggregated attributes over intersecting polygons before presenting all 288 attributes as equally interpretable. This review does not establish that every upstream-derived attribute is wrong.

### 3. Fix the CF-1.8 claim and packaging

`06_data_records.tex:36` claims CF-1.8 time-series conventions. Direct inspection of all three released NetCDFs found only `gauge_id` and `time` coordinates, with no latitude/longitude, projected spatial coordinates, or embedded geometry. The global `Conventions = CF-1.8` attribute is not sufficient: [CF-1.8 §9.5](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.8/cf-conventions.html#_coordinates_and_metadata) requires association with spatial and temporal coordinates.

Add appropriate station auxiliary coordinates/metadata through the packaging code and validate the resulting files with a compliance checker before retaining the claim. An external GeoPackage join helps users but does not establish each NetCDF's claimed compliance. Release edits require a separately authorised revision; none were made here.

### 4. Remove factual overstatements contradicted by the paper itself

- `01_introduction.tex:14` and `10_conclusions.tex:4`: distinguish visual inspection of all 3353 boundaries from area comparisons for the 3011 with reference areas. There are 342 without reference areas.
- `10_conclusions.tex:6`: not every failed check ships as a flag. `07_validation.tex:15–17` explicitly leaves nested violations unflagged, including 31 pairs with neither gauge flagged by the other screens.
- `07_validation.tex:4`: nested checking does not cover the most gauges; its 1798 are fewer than the stage–discharge check's 2106.
- `06_data_records.tex:57`: the text says seven known artefacts, but the table lists eight.
- “Observed days” in signature descriptions includes available interpolated discharge: `create_paper_signatures.py` reads values without filtering `quality_flag`. The release has 1691 filled discharge gauge-days. Use precise provenance language or change the calculation explicitly.

These findings show why numerical macro synchronization cannot substitute for a prose review.

### 5. Limit statistical and causal claims to what was tested

The Mann–Whitney significance claims at `07_validation.tex:62` ignore known gauge dependence. The bootstrap in `scripts/plot_coldregion_gradient.py:51` resamples individual gauges, without spatial/river-network blocks. Descriptive contrasts remain useful, but the intervals do not account for nesting. For this descriptor, reporting medians and spread without population-level significance claims is a simpler defensible option; retain formal inference only with a justified resampling unit.

Several explanations should be hypotheses rather than findings: a shorter open-water window increasing noise without removing ice effects; snow-cover correlation establishing the cause of Budyko departures; sub-freezing temperature identifying actual precipitation phase; and filter timescales conclusively explaining the BFI gradient. The warning that filter-derived BFI is not a measured groundwater fraction is sound and should remain.

Call the A–F system a reproducible screening/consistency grade. It is not an independent calibration of observational accuracy. Preserve the strict Grade-A definition; these findings do not justify changing grading thresholds.

## Figure assessment

All included assets were visually inspected. The current light basemaps, consistent projection, sequential signature palettes, and precipitation difference panels are useful. Most figures should be retained and corrected, not discarded.

| Figure | Assessment and revision |
|---|---|
| 1: network and basin sizes | Clear at manuscript scale; map legend and area classes sum to 3201. Add a few river/region or graticule labels to orient an international reader. Explain abbreviated climate classes. Keep the lighter terrain treatment. |
| 2: workflow | Scientifically incomplete arrows: signatures appear to derive from HydroATLAS alone, without discharge/forcing/area inputs. The “area weights” arrow implies a procedure not used for most forcing catchments. The ≤6-day label omits the 15-day reservoir-stage exception, and grading should be explicitly discharge-only. Correct the information flow. |
| 3: quality | Readable and consistent with grade counts. Retain the distinction between overall grade and share of assessed years graded A. Do not equate yellow with independently proven accuracy. |
| 4: precipitation differences | Stronger than three similar absolute-precipitation maps. Unequal discrete intervals should be identified as classes. Mark out-of-range colours explicitly; current edges are derived from a robust percentile, not full extrema. Differences are not measured product errors. |
| 5: Budyko | Useful diagnostic; revise interpretation as described above. Report per-panel counts outside the axes instead of “a few,” and label the envelope as conditional on balance/PET assumptions. Avoid implying that distance from the curve ranks forcing accuracy. |
| 6: cold-region example | Change “DOY” to “day of hydrological year” or month labels. The caption explains the October origin, but the axis should stand alone. Prefer a linear temperature colour scale to the asymmetric −5 °C midpoint. Resolve dependent-gauge uncertainty and give sample sizes for all bins. Keep this a short demonstration of reuse. |
| B1–B4: signature maps | Keep the map-plus-distribution concept. Fix unlabelled overflow colours, specify quantile orientation in panel titles, add panel-specific sample/missing counts, and supply numeric histogram counts or a small frequency axis. B4 is missing panel letters although the caption uses (a)/(b). |

**Confirmed legend problem:** `src/plots/paper_maps.py:162` clips values into the outer histogram classes; the map uses the same end colours without an extended colourbar. Direct comparison with non-anomalous release signatures gives:

| Mapped quantity | Displayed limits | Values outside limits |
|---|---:|---:|
| Mean discharge | 0–8 mm/day | 1 |
| Q95 low flow | 0–2.5 mm/day | 3 |
| Q05 high flow | 0–20 mm/day | 3 |
| BFI | 0.20–0.85 | 7 |
| Half-flow date | days 120–270 | 90 |
| FDC slope | 0–15 | 0 |
| High-flow frequency | 0–50% | 0 |
| Low-flow frequency | 0–70% | 2 |

The half-flow-date maximum is 295.417, so a reader can incorrectly interpret late dates as belonging to the 240–270 class. Use explicit open-ended classes/extension markers or extend the range. These points are not absent from the map; their magnitude is not adequately represented by the legend. There are 1641 defined half-flow dates versus 1716 records overall. The plotting code also draws missing values in grey (`show_nan=True`) while captions say undefined metrics are omitted; align the caption and actual rendering.

### Dissertation references

Inspected `Development/Dissertation/res/chapter_one/geo_dist_Hydrogeology_and_Cryosphere.png`, `map_hybrid_classes_watersheds.png`, and archived `conclusions/images/q5q95bfimean.png` (plus an archived clustering diagnostic). The useful transferable ideas are an explicit distribution beside spatial patterns, readable watershed boundaries, and consistent panel structure. The paper already adopts part of this through colourbar histograms.

Do not copy the older dark-grey backdrop or dense four-map layout wholesale. Do not copy normalised/winsorised values into a descriptor where physical units and extremes matter. Hex aggregation could obscure sparse coverage and individual flagged gauges; it is optional for a separate regional summary, not a necessary replacement for the gauge maps. One additional coverage-through-time figure would serve data reuse better than another decorative map: distinguish observed, filled, missing, and unavailable records.

## ESSD submission requirements and unresolved evidence

[ESSD review criteria](https://www.earth-system-science-data.net/peer_review/review_criteria.html) emphasise utility, quality, and clear, concise presentation. At 51 review-format pages, streamline repeated caveats and move detailed grading sensitivity/reference material to a supplement while retaining the primary validity checks. Page count alone is not a rejection rule.

[ESSD data policy](https://www.earth-system-science-data.net/policies/data_policy.html) allows anonymous repository review links at submission and requires a functional DOI at publication. The manuscript contains a DOI and a preview link, but anonymous access and uploaded-file parity remain unverified here. Check those against the release manifest before submission. Freeze an immutable code version; `main.tex:109` currently postpones the release tag until acceptance.

The data-availability statement reasons from unrestricted public portal access to a CC BY release. That is an evidence gap to resolve, not a finding that redistribution is unlawful. Document the applicable source terms, permission, or public-data status, and distinguish rights in source observations from rights in derived products. [Creative Commons guidance](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-someone-elses-work) requires authority over the rights being licensed.

Given the reported co-author situation, confirm the author list, contributions, affiliations, and final submission agreement. [ESSD author obligations](https://www.earth-system-science-data.net/policies/obligations_for_authors.html) require all named authors to have seen and agreed to the final submission. Lack of current help does not alone settle appropriate authorship.

Also review the existing AI-use statement against actual drafting history. [ESSD's current AI policy](https://www.earth-system-science-data.net/policies/ai_policy.html) permits assistive language editing but prohibits generative AI text or interpretations. This internal review can identify issues for author resolution; it should not be pasted into a submitted referee report, or used to claim that an autonomously generated scientific rewrite is author-written. No determination about the historical statement's truth was made here.

## Journal recommendation and costs

Keep **ESSD first**, and pursue institutional support or a waiver if cost is a barrier. A publication charge pays for publishing; it does not purchase acceptance. Open access for readers does not automatically mean free publication for authors.

| Journal | Verified current fee information | Fit for this manuscript |
|---|---|---|
| ESSD | €1400 net list price; qualifying institutional-agreement price €1260; country waivers and discretionary support exist | Best fit for a CAMELS data descriptor. |
| HESS | €1800 net full-article list price, with discounts/waivers | Possible hydrological-science venue, but not a cheaper default or a reason to undo the descriptor framing. |
| Scientific Data | €2390 / £2150 / US$2690, before applicable taxes; price determined at acceptance | Strong dataset-paper alternative, but not a cost-saving switch. |
| Journal of Hydrology and Hydromechanics | No submission or publication fee, according to the journal | Genuine free-OA option, but its scope prioritises process research, especially temperate-zone catchment hydrology. Q1 in the required hydrology category/database was not verified; do not treat a “best quartile Q1” directory label as proof. |

Sources checked: [ESSD fees](https://www.earth-system-science-data.net/about/article_processing_charges.html), [ESSD financial support](https://www.earth-system-science-data.net/about/financial_support.html), [HESS fees](https://www.hydrology-and-earth-system-sciences.net/about/article_processing_charges.html), [Scientific Data fees](https://www.nature.com/sdata/open-access), [JHH scope](https://journals.savba.sk/index.php/jhh/about), [JHH fees](https://journals.savba.sk/index.php/jhh/about/submissions).

ESSD discretionary waiver requests must be made **at manuscript registration**; its policy explicitly gives priority to authors without research funds, among other circumstances. Approval is not guaranteed. Exact Q1 eligibility requires the user's intended ranking database, subject category, and metric year. This review did not obtain an authoritative current JCR category extract and does not certify the alternatives as JCR-Q1 hydrology journals.

## Recommended revision sequence

1. Resolve the scientific statements above against their actual estimands; correct the proven internal contradictions. Keep the contribution focused on data preservation, usability, and transparent screening.
2. Prepare a separately versioned release revision for coordinate metadata, categorical attributes, and harmonised signature definitions. Preserve existing provenance and avoid silent replacement of the current archive.
3. Correct workflow arrows, overflow legends, date labels, and figure/caption mismatches. Retain the current visual foundation; add temporal coverage if space permits.
4. Streamline the descriptor and freeze the code/release/manuscript combination. Rebuild, rerun numerical checks, validate NetCDF conventions, and inspect the rendered figures at publication size.
5. Confirm anonymous repository access, redistribution basis, author agreement, accurate disclosures, and funding/waiver route before submission.

The evidence supports finishing the paper through targeted revision. It does not support calling the current version submission-ready or guaranteeing acceptance after cosmetic changes.
