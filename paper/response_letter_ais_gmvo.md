# AIS GMVO — response-letter material + verification checklist

Auxiliary note for the HESS submission. **Not part of the manuscript.** Holds the
administrative provenance of the AIS GMVO data source for a reviewer who asks why the
source link is dead, plus the verification record behind the wording used.

The **manuscript itself** states only the qualitative, safe timeline (portal operated by
Rosvodresursy, decommissioned September 2025, migrated to GIS CP "Voda" behind domestic
auth, static subset DOI-archived). This file keeps the response-letter prose **number-free**:
internal Rosvodresursy order numbers are dropped — they could not be verified against any
authoritative source, are Russian-only and untranslatable, and add reviewer risk for no
benefit. The *events* below are all confirmable qualitatively; only the order numbers were not.

## 1. Verification record (web-checked 2026-06-23)

Each row is the author's original recollection, the outcome of checking it against Russian
government / Rosvodresursy sources, and the resolution. **Decision: use qualitative wording,
no order numbers** (see §2).

| Author recollection | Web-verification outcome | Resolution |
|---------------------|--------------------------|------------|
| Order No. **97**, **Aug 2013** — inception/pilot | ❌ Not found in any DB. Authoritative records (cntd.ru, garant.ru, nord-west-water.ru) show AIS GMVO put into **permanent operation in 2014** — *not* 2013; the recalled number and year are both off. | ✅ **Drop number.** Wording: long-standing portal, standardized records back to 2008. |
| Order No. **297** — Digital-Transformation Program → GIS CP "Voda" | ❌ No. 297 not found. But GIS CP "Voda" is independently confirmed (Rospatent certificate Dec 2023; Gosuslugi integration from Aug 2024; commissioning announced ~Mar 2025; listed among Rosvodresursy systems on voda.gov.ru). | ✅ **Drop number.** Wording: "under Rosvodresursy's digital-transformation program." |
| Order No. **222** — formalizes decommission, Sept/Oct 2025 | ❌ No. 222 not found. The **decommission itself is confirmed first-party**: gmvo.skniivh.ru now serves "Данный ресурс выведен из эксплуатации" and redirects to the GIS CP "Voda" segments. | ✅ **Drop number.** Wording: "decommissioned in 2025." |
| Trial operation **2023–2024** | ⚠️ Not stated verbatim, but consistent with the public record (Rospatent cert Dec 2023; Gosuslugi status feed from 1 Aug 2024; formal commissioning ~Mar 2025). | ✅ Keep qualitatively as "after a transition period." |
| Decommission **9 September 2025** | ⚠️ Decommission confirmed (portal banner); the **exact day is unverified** (no public source). Month "September 2025" matches the manuscript. | ✅ Use **"September 2025"** (per manuscript); drop the day-level "9th." |
| Replacement **gis.favr.ru / sslgis.favr.ru**, ESIA/Gosuslugi auth | ✅ **gis.favr.ru confirmed** as the GIS CP "Voda" portal; closed-circuit / domestic-auth access supported by Rosvodresursy access-instruction docs ("Инструкция для получения доступа к Сегментам ГИС ЦП Вода", rwec.ru). `sslgis.favr.ru` is the plausible SSL variant, not separately confirmed. | ✅ Keep `gis.favr.ru` + closed-circuit / ESIA-Gosuslugi wording. |
| Last successful data pull: **summer 2025** | — author's own extraction date; not web-checkable. | ✅ Keep as-is. |

**Net:** the qualitative provenance narrative is fully supportable; every order number is dropped
as unverifiable. The one genuinely public administrative anchor (permanent commissioning in 2014,
Rosvodresursy Order No. 35 of 10 Feb 2014) is left out of the letter too — kept here only as a
verification footnote, not used in prose, to honor the "wording, no numbers" decision.

## 2. Draft response-letter paragraph (number-free, deploy as-is)

> The discharge and water-level records were obtained from the Automated Information
> System for State Monitoring of Water Objects (AIS GMVO, gmvo.skniivh.ru), the public
> portal of the Federal Agency for Water Resources (Rosvodresursy), which published the
> gauging-network observations of the Russian Hydrometeorological Service (Roshydromet) and
> had long served as the primary open repository for Russian hydrological monitoring data,
> with standardized digital records extending back to 2008. Under Rosvodresursy's
> digital-transformation program, AIS GMVO was superseded by the State Information System
> "Water Data" (GIS CP "Voda"); after a transition period, the legacy portal was
> decommissioned in September 2025. The replacement platform (gis.favr.ru) uses a
> closed-circuit architecture requiring domestic authentication via ESIA/Gosuslugi, so the
> URLs active during our data extraction (summer 2025) are no longer publicly resolvable —
> the AIS GMVO portal now displays only a decommissioning notice redirecting users to the
> new system. To preserve reproducibility, the exact static subset used in this study is
> permanently archived under DOI [Zenodo DOI] as part of the CAMELS-RU v1.0 release.

## 3. Figure / temporal-consistency audit (manuscript) — COMPLETE ✅

Cross-checked every date/temporal label in and around the figures against the corrected
timeline (study coverage **2008–2023**; AIS GMVO public operation 2008 → **Sept 2025**).
Swept `sections/*.tex`, `main.tex`, `macros.tex`, `tables/*.tex`, all `\caption{}` blocks and
`\includegraphics` references. **No inconsistencies found — no manuscript edits required.**

- [x] Figure captions and axis ranges in `paper/overleaf/sections/` + `images/` — consistent
      with 2008–2023. The only caption with a temporal label (`fig_precip_comparison.png`,
      "mean annual difference … over `\years`") expands to 2008–2023. All 8 figures are
      spatial maps / Budyko scatter / day-of-year seasonal hydrograph / cross-sectional
      gradients — **none has a multi-year time axis**, so no baked-in date label can conflict.
- [x] `\years` macro and every inline "2008–2023" / "16-year" statement agree.
      `macros.tex`: `\startyear{2008}`, `\studyendyear{2023}`, `\years → 2008–2023`. The two
      "16-year record" statements (07_data_records §36, 08_discussion §20) are arithmetically
      correct (2008–2023 inclusive = 16 years). 13 `\years` usages, all expand to 2008–2023.
- [x] No residual "2024"/"2025" coverage dates contradicting §3.1 / refs.bib. **Zero "2024"
      anywhere.** All six "2025" hits are the AIS GMVO public-closure date (abstract,
      03_data_methods ×2, 07_data_records, 09_conclusions, main.tex:87 "September 2025") —
      legitimate, not coverage. The "2008–2022" hits (03_data_methods §122/§124) are
      ERA5-Land tile/gap-fill technicalities; coverage is still 2008–2023 (2023 retained/filled).
- [x] precip-comparison / Budyko / signature-map period labels match the analysis window
      (precip-comparison over `\years`; Budyko & signature maps are cross-sectional, no span claim).
- [x] `pixi run python scripts/verify_macros.py` — **GREEN** ("No drift — all checked macros
      reproduce from release + audit artifacts"). Confirmed after the audit; no macros touched.
