# CAMELS-RU Codebase Guide

## Project Architecture

**CAMELS-RU** is a scientific hydrological analysis toolkit for Russian river catchments, implementing peer-reviewed algorithms for discharge time series analysis and climate index calculations.

### Core Module Structure

```
src/
├── hydro/              # Hydrological signature calculations
│   ├── base_flow.py    # Eckhardt (2005) filter with 1000 MC realizations
│   ├── flow_*.py       # Flow metrics (duration, extremes, timing, variability)
│   └── period_based_metrics.py  # Multi-year aggregation
├── meteo/              # Meteorological analysis (SPI, SPEI, drought indices)
├── timeseries_stats/   # Trend detection and statistical analysis
├── plots/              # Geospatial visualization (continuous_maps, categorical maps)
├── static/             # HydroATLAS integration and cluster analysis
├── processing.py       # Hydrological year splitting (Oct 1 - Sep 30)
└── hydro_metrics.py    # Legacy comprehensive analysis with plotting
```

### Key Conventions

**Hydrological Year**: Oct 1 - Sep 30 (use `split_by_hydro_year()` from `processing.py`)

**Data Format**: Pandas Series with DatetimeIndex, discharge in m³/s, daily frequency

**Missing Data**: Split series at gaps; analyze continuous segments only (min 300 days)

**Performance**: Core algorithms are Numba JIT-compiled (`@numba.jit(nopython=True)`)

## Development Workflows

### Running Tests

```bash
# Run all tests with pytest
pytest tests/

# Run specific test file
pytest tests/test_period_based_metrics.py -v
```

### Code Quality

```bash
# Lint with Ruff (PEP 8 + Google docstrings)
ruff check src/ tests/ scripts/

# Format code
ruff format src/ tests/ scripts/

# Type checking with Pyright (Python 3.12+)
pyright src/
```

**Important**: All linting rules are in `pyproject.toml`. Code must be PEP 8 compliant with 79-char line length, full type hints, and Google-style docstrings.

### Analysis Notebooks

Primary workflows are in `notebooks/`:
- `Hydrological.ipynb`: Discharge metrics calculation and spatial visualization (cells 11-21)
- `HydroAtlasFinal.ipynb`: Catchment clustering with HydroATLAS attributes
- `Forcings.ipynb`: Meteorological data processing

**Data paths** (configured in notebooks):
- Discharge: `data/HydroFiles/Discharge/full/decent/`
- Outputs: `paper/images/` (figures), `results/` (CSVs)

## Project-Specific Patterns

### Base Flow Index (BFI)

The BFI implementation uses **1000 Monte Carlo realizations** with random α parameters:

```python
from src.hydro.base_flow import bfi_1000

# Returns (mean_bfi, baseflow_series)
bfi_value, baseflow = bfi_1000(discharge.values, passes=3, reflect=30)
```

**Three-pass Eckhardt filter**: forward → backward → forward for smooth separation.

### Comprehensive Metrics Pipeline

For batch processing multiple catchments:

```python
from src.hydro.period_based_metrics import calculate_comprehensive_metrics

# Calculate 50+ hydrological signatures
metrics = calculate_comprehensive_metrics(
    discharge_series,
    include_bfi=True,
    include_all_modules=True
)
```

Returns flat dict with prefixed keys: `baseflow_*`, `fdc_*`, `extreme_*`, `timing_*`, `variability_*`

### Logging System

Centralized logger in `src/utils/logger.py`:

```python
from src.utils.logger import setup_logger

logger = setup_logger("module_name", log_file="logs/analysis.log")
logger.info("Processing station: %s", station_id)
```

Logs written to `logs/` directory (git-ignored). Use for debugging, not production outputs.

### Geospatial Visualization

Two plotting approaches:
1. **Continuous metrics**: `src/plots/continuous_maps.py` for quantitative data
2. **Categorical data**: `src/plots/maps.py` for cluster/classification results

Both require catchment geometries and use discretized color schemes (n_bins parameter).

## External Dependencies

### Data Sources

**GLEAM evapotranspiration**: Downloaded via `scripts/gleam_loader.py` (SFTP client)

```bash
python scripts/gleam_loader.py --version v4.2a --freq daily --years 2008:2023
```

**ERA5-Land**: Handled by `src/meteo/era5_land_loader.py` and `scripts/load_era5_land.py`

### HydroATLAS Integration

Catchment attributes from `src/static/hydro_atlas_reader.py`:
- Uses pre-computed shapefiles with physiographic attributes
- Clustering performed with `src/static/cluster_tools.py`
- Results drive spatial stratification in analysis workflows

## Common Pitfalls

1. **Runoff ratio placeholder**: Current implementation uses 600mm/year precipitation constant (see `docs/analysis_summary.md` limitations)
2. **BFI parameter**: Uniform α across catchments; future work will regionalize this
3. **Trend analysis period**: Limited to 16 years (2008-2023) in current dataset
4. **Import paths**: Always use `from src.module` (not relative imports)

## Scientific Rigor

All implementations reference peer-reviewed literature:
- Eckhardt (2005) for base flow separation
- Addor et al. (2018) for hydrological signatures
- Newman et al. (2015) for CAMELS framework

Validate new methods against published examples before integration. Document random seeds for reproducibility.

## Testing Philosophy

Tests in `tests/` use pytest with fixtures:
- Test with synthetic data (controlled random seeds)
- Verify edge cases (NaN handling, minimum data requirements)
- No integration with actual data files (kept in git-ignored `data/`)

**Current coverage**: Base flow, period-based metrics, logging system
