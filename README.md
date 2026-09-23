# CAMELS-RU: A Large-Sample Hydroclimatic Dataset for 3,353 Russian Catchments

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)
[![License: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

A hydrological dataset following the CAMELS framework for the Russian Federation, covering 3,353 catchments with daily discharge, water level, meteorological forcing, physiographic attributes, and hydrological signatures (2008–2023).

**Paper**: The active collaborative manuscript source is the Overleaf submodule at `paper/overleaf/` (target: Earth System Science Data, ESSD)
**Dataset**: Zenodo DOI [10.5281/zenodo.22132299](https://doi.org/10.5281/zenodo.22132299) — reserved; the record goes live upon paper acceptance

## Dataset Summary

| Component | Coverage |
|-----------|----------|
| Catchments | 3,353 visually inspected watersheds; area comparison for 3,011 with reference areas (trimmed mean error 5.1%) |
| Discharge | 2,170 gauges, daily, 2008–2023 (936 Grade A, 86% decent quality) |
| Water level | 2,989 gauges, daily, 2008–2023 |
| Forcing | ERA5-Land (T) + GLEAM4 (PET) + MSWEP v2.8 (P), basin-averaged |
| Attributes | 281 HydroATLAS attributes + 7 derived = 288 columns per catchment (22 primary subset) |
| Signatures | 16 hydrological metrics for 1,729 gauges (1,716 non-anomalous rows used in the main-text figures) |
| Quality control | Per-year grading (A–F), strict Grade A (all years must be A) |

## Release metadata and reuse

The frozen v1.0 package is distinct from the generated **local v1.1 CF-1.9
candidate** at `release/CAMELS_RU_v1.1_cf19/`, which is not yet archived/published.
All three NetCDFs pass strict CF-1.9 checks. The tracked
[README](paper/metadata/README_v1.1_cf19.md) and
[changelog](paper/metadata/CHANGELOG_v1.1_cf19.md) specify its scope.

[Signature definitions](paper/metadata/signature_crosswalk.json) cover 16 signatures
and three ERA5-Land variants; annual averaging, thresholds, quantile orientation, gaps
and interpolation prevent automatic cross-CAMELS harmonisation.
[Attribute metadata](paper/metadata/hydroatlas_metadata.json) covers 281 source plus
seven derived fields. Exclude the eleven invalid categorical means (`*_smj`); other
attributes, including the primary 22, retain documented spatial-support qualifications.
The [loading example](examples/load_camels_ru.py) reads this guidance for v1.0 or v1.1.

## Quality Grading

Discharge time series are graded per hydrological year (Oct–Sep) using 21 defined flag types; the release-default grading evaluates 16 active flags (two variance flags and three optional temperature-aware effective-water flags are disabled by default). A gauge receives overall Grade A only if **every** assessed year is individually graded A. These are reproducible screening/consistency grades, not independently calibrated observational accuracy; inspect the separate provenance and diagnostic flags for the intended use.

The release includes `year_grades.csv` — a per-gauge × per-year grade matrix — so modelers can filter out D/F years from calibration/validation windows.

## Project Structure

```
camels_ru/
├── src/                      # Core analysis modules
│   ├── hydro/               # Hydrological signatures (BFI, FDC, timing, extremes)
│   ├── meteo/               # Meteorological aggregation (ERA5, MSWEP, GPCP)
│   ├── quality/             # Discharge quality grading (A–F per year)
│   ├── data_processing/     # Geospatial and NetCDF utilities
│   ├── timeseries_stats/    # Trend analysis (Mann-Kendall, Sen's slope)
│   ├── plots/               # Publication-quality cartographic functions
│   ├── static/              # HydroATLAS extraction and clustering
│   └── utils/               # Logging and helpers
├── scripts/                 # Data processing pipeline
├── notebooks/               # Analysis notebooks (with .py parallels) + delineation utilities
├── examples/                # Minimal dataset-loading example (load_camels_ru.py)
├── tests/                   # Self-checking test scripts (run by CI)
├── paper/                   # ESSD manuscript assets
│   ├── overleaf/            # Active manuscript source (git submodule, Overleaf remote)
│   └── images/              # Canonical manuscript figures, mirrored into overleaf/images/
├── app/                     # FastAPI web interface for quality review
└── release/                 # Zenodo dataset package (gitignored)
```

## Data Processing Pipeline

```
AIS GMVO (XLS) → ParseAis*.py → Compound CSVs
                                      ↓
ERA5-Land/MSWEP/GPCP → aggregate_watersheds.py → per-gauge forcing
                                      ↓
                              GradeCompound.py → quality grades (A–F)
                                      ↓
                         create_year_grades.py → year_grades.csv
                                      ↓
                    create_forcing_netcdf.py → forcing NetCDF-4
                                      ↓
        package_dataset.py → discharge/water-level NetCDF-4 + Zenodo release
```

## Installation

```bash
git clone git@github.com:HydroInformaticsRu/camels_ru.git
cd camels_ru
pixi install        # Python 3.12+, all dependencies
```

## Data Access

The dataset is not included in this repository. To use the analysis tools:

1. Download CAMELS-RU from Zenodo: DOI [10.5281/zenodo.22132299](https://doi.org/10.5281/zenodo.22132299) (the record goes live upon paper acceptance).
2. Symlink the data directory:
   ```bash
   ln -s /path/to/camels_ru_data data
   ```

## Key Dependencies

- **Core**: Python 3.12+, NumPy, Pandas, SciPy, Numba
- **Geospatial**: GeoPandas, Rasterio, Xarray, pyproj
- **Visualization**: Matplotlib, Cartopy
- **Web**: FastAPI (quality review app)

## Citation

Abramov, D. V., Maximov, Y., Tsyplenkov, A., and Moreido, V.: CAMELS-RU: hydrometeorological time series and catchment attributes for 3353 Russian catchments, 2008–2023, Earth Syst. Sci. Data (in review), 2026. See `CITATION.cff`.

## Acknowledgments

- Roshydromet / AIS GMVO — discharge and water level observations
- HydroATLAS (Linke et al., 2019) — catchment attributes
- MERIT Hydro (Yamazaki et al., 2019) — watershed delineation
- MSWEP (Beck et al., 2019) — precipitation forcing
- ERA5-Land (Muñoz-Sabater et al., 2021) — temperature forcing
- GLEAM4 (Miralles et al., 2025) — potential evapotranspiration forcing

## License

- **Code**: MIT License — see [LICENSE](LICENSE)
- **Dataset**: CC BY 4.0

## Contact

**Author**: Dmitrii V. Abramov
**Email**: dmbrmv@icloud.com

The preferred local candidate passes complete numerical-preservation and strict
CF-1.9 checks; see [the validation report](paper/reviews/CF19_VALIDATION_2026-09-23.md).
It stores `gauge_id(station)`; the loading helper supports both layouts. The frozen
v1.0 and first v1.1 candidate remain untouched. The first candidate's failed CF-1.8
checks are preserved in [the earlier report](paper/reviews/CF_VALIDATION_2026-09-23.md).
