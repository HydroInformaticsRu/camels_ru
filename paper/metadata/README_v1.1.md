# CAMELS-RU v1.1 — local metadata amendment candidate

A large-sample hydroclimatic dataset for 3,353 Russian catchments following the CAMELS framework.

This is the tracked README source for a proposed local v1.1 candidate. It is
based on the frozen v1.0 README. Version 1.1 is not yet archived or published, and this
README does not certify CF compliance. No new DOI is assigned here. Consult the
repository submission gate for author approval, source redistribution rights, and
repository access checks before publication. The proposed data licence remains subject
to that evidence review; public access to source observations alone does not establish
redistribution rights. Processing code is available under the repository MIT licence.

The amendment adds station coordinate metadata to NetCDFs and the two JSON sidecars
below. Numerical time series, interpolation/provenance flags, grades, signatures,
attributes and catchment boundaries remain unchanged. See `CHANGELOG.md`.

## Metadata and interoperability

`signature_crosswalk.json` describes all 16 signatures plus three ERA5-Land variants:
units, exact code definitions, aggregation, masks, gaps and qualified external comparisons.
This is a definition crosswalk, not a harmonised signature product. In CAMELS-US
(Addor et al., 2017), `Q95` is high flow and `Q5` is low flow; CAMELS-RU `q05` and `q95`
use exceedance orientation. Renaming cannot remove annual-versus-whole-record
aggregation differences. High-flow thresholds are 2 versus 9 times median, and CAMELS-RU
frequencies are percentages of available days rather than days/year. Comparator source
versions are explicit; no universal Caravan equivalence is asserted.

`hydroatlas_metadata.json` covers exactly 288 value columns: 281 HydroATLAS source
attributes and seven derived fields, excluding `gauge_id`. Its eleven `*_smj` fields
have `usability="invalid_category_mean"` and `recommended_for_analysis=false`. They
remain numerically unchanged for provenance: do not round them into classes. Other
fields have qualified support/aggregation guidance, including the primary 22 subset.
An area-weighted average of upstream, pour-point or sum attributes is not automatically
the corresponding quantity for the CAMELS-RU catchment. Check units as released:
`gdp_ud_sav` is GDP per capita, and `hdi_ix_sav` retains the source's x1000 scale.

Both sidecars describe the unchanged v1.0 values as well as v1.1. The v1.0 archive itself
is frozen; repository examples can read its attributes with these tracked sidecars.
Station auxiliary coordinates added to the three candidate NetCDFs are documented by
the packaging code and verification report. A `Conventions` string is not evidence of a
passed CF compliance checker; checker status must be reported separately.

## Contents

| File | Format | Description |
|------|--------|-------------|
| `camels_ru_boundaries.gpkg` | GeoPackage | 3,353 catchment boundary polygons with `gauge_id`, `name`, `area_km2`, `area_roshydromet`, and `area_diff_perc` |
| `camels_ru_discharge.nc` | NetCDF-4 | Daily discharge (`discharge_mm` mm d⁻¹, `discharge_m3s` m³ s⁻¹) plus `quality_flag` (0 = observed, 1 = gap-filled, 3 = missing) and the per-gauge `specific_discharge_anomaly` (1 = median `discharge_mm` > 20 mm d⁻¹, a potential inconsistency requiring area, discharge and forcing checks; −1 = no record), 2008-01-01 to 2023-12-31. Gauge dimension covers all 3,353 catchments; 2,170 of these carry observations, the remaining 1,183 are all-missing placeholders for alignment with `boundaries.gpkg`. |
| `camels_ru_forcing.nc` | NetCDF-4 | Daily meteorological forcing for 3,353 catchments: `precip_mswep` (MSWEP v2.8, mm d⁻¹; primary), `precip_era5` / `precip_gpcp` (ERA5-Land de-accumulated / GPCP v3.3 precipitation, mm d⁻¹; shipped for the forcing intercomparison), `temp_mean/min/max` (ERA5-Land, °C), `pet` (GLEAM4 potential evapotranspiration, mm d⁻¹). 100% coverage of the primary variables; temperature gaps filled for 7 gauges (see "Forcing coverage & gap-fill" below). |
| `camels_ru_attributes.csv` | CSV | 281 HydroATLAS attributes (full BasinATLAS v1.0 set; area-weighted means over the intersecting HydroBASINS level-12 polygons, normalised per variable) plus 7 CAMELS-RU-derived columns — 288 attribute columns plus the `gauge_id` key — for 3,339 catchments (14 very small catchments lack HydroATLAS coverage). `height_bs` is the MERIT Hydro DEM elevation at the gauge location; `area_fraction_used` and `n_hydroatlas_polygons` are extraction diagnostics. Categorical class-code columns (suffix `_smj`) are invalid area-weighted means of class codes and are excluded from the recommended feature set by `hydroatlas_metadata.json`; no replacement class is supplied. |
| `camels_ru_signatures.csv` | CSV | 16 hydrological signatures per gauge (1,729 rows; 13 flow descriptors with CAMELS-family counterparts only where verified, the Budyko `aridity_index` and `evaporative_index`, and `winter_flow_ratio`), computed from `camels_ru_discharge.nc`, `camels_ru_forcing.nc` and the areas in `camels_ru_boundaries.gpkg` alone over the 15 complete hydrological years 2009–2023 (a year counts when ≥ 70 % of its days carry discharge; ≥ 5 valid years required; `n_valid_years` gives the count; catchments < 50,000 km²). Water-balance signatures use MSWEP precipitation on paired days; `runoff_ratio_era5`, `aridity_index_era5`, `evaporative_index_era5` are the ERA5-Land variants. 13 rows are flagged `is_anomalous` (q_mean > 20 mm d⁻¹ from sub-50 km² basins: three delta distributaries, five Kamchatka streams whose delineated area is likely underestimated, and five streams whose reported discharge is implausible) and are excluded from `camels_ru_signatures_summary.csv`; the manuscript figures use the 1,716 non-anomalous rows. `winter_flow_ratio` is mean January–March discharge over mean annual discharge on available days, including interpolated discharge, and `winter_coverage` gives the share of January–March days available, including interpolated Q (the same window as the ratio): the archive omits under-ice values at many gauges, so screen on `winter_coverage` (the manuscript uses ≥ 0.95) before using it. It describes cold-season yield; the filter-derived `baseflow_index` should not be interpreted as a measured groundwater fraction, especially in snow-dominated regimes. `water_balance_screen` marks 118 rows of the full file — the 105 non-anomalous gauges whose multi-year `runoff_ratio` exceeds 1, plus the 13 anomalous rows, a conditional consistency diagnostic under incomplete-period, storage and import assumptions rather than proof of a specific physical error; 73 of them hold the strict grade A, so **screen on it independently of the grade**. Note that `q05`/`q95` are *exceedance* percentiles, so `q05` is the high-flow and `q95` the low-flow quantile — the opposite orientation to the CAMELS-US Q5/Q95 names; consult the crosswalk for version-specific comparisons. |
| `camels_ru_signatures_summary.csv` | CSV | Per-signature summary statistics (n, mean, median, min, max, std) across non-anomalous gauges. |
| `camels_ru_year_grades.csv` | CSV | Per-gauge × per-hydro-year quality grade (A–F) for the 2,065 graded gauges (grading needs ≥ 3 years of observations and ≥ 3 complete hydrological years; hydro-year N = Oct N−1 to Sep N), computed on the released `camels_ru_discharge.nc`. The 105 ungraded discharge gauges are absent from this file and from `camels_ru_gauge_summary.csv`. |
| `camels_ru_year_flags.csv` | CSV | The evidence behind every year grade: one row per assessed gauge-year (28,668 rows) with `gauge_id`, `hydro_year`, `grade`, `completeness` (the year's data completeness — a grade input alongside the flags, via the 70/85/95 % caps), and the comma-separated quality-flag codes (`flag_codes`; empty = no flag fired). Regenerates from the released files alone (`scripts/create_year_flags.py` in the code repository), so the grading is auditable row by row. |
| `camels_ru_gauge_summary.csv` | CSV | Per-gauge overall grade, year counts (n_A…n_F), worst-grade, recommendation, and `forcing_note` (populated for the one graded discharge gauge among the 7 gauges with gap-filled ERA5-Land temperature; of the other six, one (1508) carries water level only and five carry no time series; all seven are documented in `camels_ru_forcing_notes.csv`). |
| `camels_ru_forcing_notes.csv` | CSV | Per-gauge fill provenance for all 7 gauges with gap-filled ERA5 temperature (all east of 170°E). |
| `camels_ru_water_level.nc` | NetCDF-4 | Daily water level for 2,989 gauges. `water_level_cm` is stage above the gauge zero-post (cm); `water_level_mbs` is absolute elevation above the Baltic Height System 1977 (m). `quality_flag` marks every altered value: 0 = observed, 1 = gap-filled (gaps of ≤ 6 days, 15 for reservoir gauges, bounded by observations on both sides; 10,035 gauge-days), 2 = a reported stage of exactly 0 cm replaced by the gauge's day-of-year median (153,563 gauge-days, 1.0 % of values, 617 gauges; the export uses 0 for missing at some gauges and a genuine zero stage cannot be told apart), 3 = missing. Fills and replacements that fell outside the gauge's own observed range were reverted to missing (3,420 values at 89 gauges, 2.0 % of all altered values), which removed 991 negative stages; the released series has a minimum of 0.5 cm. Filter `quality_flag == 0` for an observed-only series. Per-gauge variables: `gauge_zero_m` (zero-post elevation), `gauge_type` (−1 = no water-level record, 0 = river, 1 = reservoir/hydropower; 152 reservoir/hydropower gauges included), and `stage_discharge_screen` (−1 = not assessed, 0 = consistent, 1 = inconsistent). The screen is the Spearman rank correlation between `water_level_cm` and `discharge_m3s` over days observed in both files, restricted to the open-water months May–October because backwater shifts the rating under ice; the median is 0.93 and 188 of 2,106 assessed river gauges fall below 0.5, including 22 whose stage falls as discharge rises. The screen is a consistency diagnostic, not independent validation of either record; consider its assessment window and local hydraulic conditions. Discharge values at these gauges are unchanged. |
| `signature_crosswalk.json` | JSON | Versioned definitions and non-equivalence limitations for 19 signature columns. |
| `hydroatlas_metadata.json` | JSON | Units, spatial support and usability of all 288 attribute value columns. |
| `CHANGELOG.md` | Markdown | Scope of the v1.1 metadata amendment and unchanged-data guarantees to verify. |

## Dimensions

- **Catchments:** 3,353 with delineated watersheds (area 0.49 to 2,670,000 km²; median 2,827 km²)
- **Discharge gauges:** 2,170 with observed data (of which **936 Grade A** under the strict rule: every assessed year graded A)
- **Water level gauges:** 2,989, including 152 reservoir/hydropower stations
- **Period:** 2008-01-01 to 2023-12-31 (5,844 days)
- **Coordinate system:** WGS84 (EPSG:4326)
- **Missing data:** `NaN` throughout, in every file and variable — never `0`, `-9999`, or any other sentinel. (The one deliberate negative code is the per-gauge `gauge_type = -1` / `stage_discharge_screen = -1` / `specific_discharge_anomaly = -1` "not applicable" class, documented per file below.)

## Identifiers & joining files

Every file is keyed on `gauge_id`, the gauge identifier. It is a **string** coordinate in the three NetCDF files (`camels_ru_*.nc`) and the `gauge_id` field in `camels_ru_boundaries.gpkg`; in the CSV tables it is an integer-valued column. The values are identical and the integer↔string cast is lossless, but a naïve `pandas.merge` of an integer CSV column against the string NetCDF coordinate returns an empty result — cast to a common type first, e.g. `df["gauge_id"] = df["gauge_id"].astype(str)`. The NetCDF time-series variables are indexed by this `gauge_id` coordinate (`cf_role = "timeseries_id"`, `featureType = "timeSeries"`).

## Quality grading (discharge)

Grades are reproducible screening/consistency categories, not independent calibration of observational accuracy. Each discharge time series is graded per hydrological year (Oct–Sep) using 16 active quality flags (21 defined, 5 disabled by default: 2 variance-based and 3 optional temperature-aware effective-water flags). Overall Grade A requires *every* assessed year to be Grade A; grades B–D use the mode of non-F year grades with usable-fraction caps. Grade distribution:

| Grade | Definition | Count |
|-------|-----------|-------|
| A | All assessed years A (≥ 95% completeness, ≤ 2 minor flags) | 936 |
| B | Mostly A/B; 3–4 minor flags or < 95% completeness | 807 |
| C | ≥ 5 minor flags or 1 major flag or < 85% completeness | 130 |
| D | ≥ 2 major flags or < 70% completeness | 178 |
| F | Any critical flag | 14 |

Decent-quality (A–C) comprises 86% of discharge gauges (1,873 of 2,170). Grades B–D use the mode of the non-F year grades with ties resolved to the worse grade (a mode of A with any non-A year gives B), capped at C when fewer than 70 % of assessed years are C or better and at D when fewer than half are; hydrological years without any observation inside a record are not assessed and are left blank in `camels_ru_year_grades.csv`. Runs of ≥ 30 identical observations raise the major `constant_value` flag only outside the November–April ice period, when piecewise-constant series are Roshydromet's under-ice reporting convention. The precipitation–discharge cross-correlation check shifts discharge by calendar days and needs ≥ 30 paired days, so incomplete years are evaluated on their observed pairs.

## Quality flags (`discharge.nc`)

| Value | Meaning |
|-------|---------|
| 0 | Observed (provenance code, not an independent accuracy certification) |
| 1 | Gap-filled (gap of ≤ 6 days bounded by observations on both sides, second-order polynomial interpolation) |
| 3 | Missing |

`specific_discharge_anomaly` (per gauge) marks gauges whose median runoff depth exceeds 20 mm d⁻¹: delta distributaries, catchments whose delineated area is underestimated, and small creeks whose reported discharge is implausible for a reference area that agrees with the delineation (most likely a unit error at source, which the closed archive does not allow us to confirm). `discharge_m3s` is released unchanged; exclude these gauges from specific-discharge and signature work.

Gap-filled values (gaps of ≤ 6 days between observations, second-order polynomial; 1,691 gauge-days) are written in place of the originals and flagged as `quality_flag = 1`. Users needing a strict observed-only subset should filter to `quality_flag = 0`.

## Quality flags (`water_level.nc`)

| Value | Meaning |
|-------|---------|
| 0 | Observed |
| 1 | Gap-filled (gap of ≤ 6 days, 15 for reservoir gauges, bounded by observations on both sides; 10,035 gauge-days) |
| 2 | Zero reading (0 cm) replaced by the gauge's day-of-year median (153,563 gauge-days at 617 gauges) |
| 3 | Missing |

Water level carries no A–F grade; assess per-gauge completeness before use.

## Forcing variables (`forcing.nc`)

| Variable | Source | Unit |
|----------|--------|------|
| `precip_mswep` | MSWEP v2.8 | mm d⁻¹ |
| `precip_era5` | ERA5-Land (de-accumulated) | mm d⁻¹ |
| `precip_gpcp` | GPCP v3.3 | mm d⁻¹ |
| `temp_mean` | ERA5-Land | °C |
| `temp_min` | ERA5-Land | °C |
| `temp_max` | ERA5-Land | °C |
| `pet` | GLEAM4 | mm d⁻¹ |

**`precip_mswep` is the recommended primary precipitation forcing.** `precip_era5` and `precip_gpcp` are the two alternative precipitation products compared in the manuscript forcing intercomparison; they are shipped so that analysis is reproducible from the release alone. `precip_era5` is the corrected, de-accumulated ERA5-Land total precipitation (earlier ERA5-Land precipitation in pre-release versions was over-accumulated and has been superseded). The three products differ in annual mean (basin-mean ≈ 609 / 705 / 661 mm yr⁻¹ for MSWEP / ERA5-Land / GPCP) but agree closely in daily pattern; see the manuscript for the full intercomparison.

## Forcing coverage & gap-fill

`forcing.nc` ships with 100% coverage for all 3,353 gauges × 5,844 days × the five primary variables (`precip_mswep`, `temp_mean/min/max`, `pet`). MSWEP precipitation and GLEAM4 PET required no fill. The two intercomparison precipitation products are not gap-filled: `precip_era5` has full coverage and `precip_gpcp` is 99.4% complete (`NaN` on 96 days with missing source cells over part of the domain, clustered in 2010, 2020, and 2022, affecting 1,584 gauges; drop pairwise or scale by coverage, never count as zero). ERA5-Land temperature required fill for 7 gauges:

| Class | Gauges | N | Fill method |
|-------|--------|---|-------------|
| **Domain edge (east of 170°E)** | 1433, 1434, 1507, 1508, 1587, 1611, 2241 | 7 | Nearest valid land cell near 170°E from raw ERA5-Land tiles for 2008–2022; native aggregation retained for 2023 (where tiles cover a wider domain). Gauge 1611 used 169°E because the 170°E cell at 69.6°N is masked as Chaunskaya Bay. |

An earlier build also filled 17 gauges flagged with a 2023 partial-tile gap; that gap was traced to a stale grid-unkeyed weight cache and resolved by re-aggregating temperature with a grid-keyed cache, so those gauges now carry real 2023 aggregation and need no fill.

Provenance is traceable through:

- `gap_fill_method` and `gap_fill_n_gauges_affected` global attributes on `forcing.nc`
- `forcing_note` column in `gauge_summary.csv` (1 entry: the only filled gauge that is graded)
- `forcing_notes.csv` — full table for all 7 filled gauges

See the Time series data section of the paper for the full methodology.

## Data sources

- **Discharge / water level:** AIS GMVO (Federal Agency for Water Resources, Rosvodresursy, publishing Roshydromet gauging-network data; public portal decommissioned September 2025 — CAMELS-RU preserves this archive)
- **Watershed boundaries:** MERIT Hydro DEM (Yamazaki et al., 2019) + visual inspection of all 3,353 boundaries; area comparison for 3,011 with Roshydromet reference areas (trimmed mean error 5.1%)
- **Meteorological forcing:** MSWEP v2.8 (precipitation; Beck et al., 2019); ERA5-Land (temperature; Muñoz Sabater et al., 2021); GLEAM4 potential evapotranspiration
- **Physiographic attributes:** HydroATLAS v1.0 (Linke et al., 2019)

## Citation

Please cite:

1. The final author-approved CAMELS-RU paper citation when available; no publication or author approval is certified by this candidate
2. HydroATLAS — Linke et al. (2019)
3. MERIT Hydro — Yamazaki et al. (2019)
4. MSWEP — Beck et al. (2019)
5. ERA5-Land — Muñoz Sabater et al. (2021)
6. GLEAM4 — Miralles et al. (2025)
7. AIS GMVO — Federal Agency for Water Resources (Rosvodresursy) (2025), https://gmvo.skniivh.ru/ (decommissioned September 2025)

## Code

Processing code: https://github.com/HydroInformaticsRu/camels_ru

## Contact

Dmitrii V. Abramov — dmbrmv@icloud.com
