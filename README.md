# CAMELS-RU: A Hydrological Dataset for Russia

## Overview

CAMELS-RU is a comprehensive hydrological dataset for Russia providing catchment attributes, meteorological forcing data, and hydrological analysis tools. This project creates a CAMELS-type dataset tailored for Russian river basins, following standards established by Newman et al. (2015) and Addor et al. (2017).

## Project Structure

```
camels_ru/
├── src/                      # Core analysis modules
│   ├── hydro/               # Hydrological metrics and signatures
│   ├── meteo/               # Meteorological data processing and analysis
│   ├── data_processing/     # Geospatial and NetCDF utilities
│   ├── quality/             # Discharge quality assessment and grading
│   ├── timeseries_stats/    # Trend analysis and statistical tests
│   ├── plots/               # Visualization and cartographic functions
│   ├── static/              # HydroATLAS and clustering tools
│   └── utils/               # Logging and utilities
├── scripts/                 # Command-line data processing tools
├── app/                     # Web interface for data quality review
├── notebooks/               # Jupyter analysis notebooks
└── paper/                   # Manuscript (Copernicus/ESSD template)
```

## Core Components

### 1. Hydrological Analysis (`src/hydro/`)

Calculate comprehensive hydrological signatures and metrics:

```python
import pandas as pd
from src.hydro import calculate_comprehensive_metrics

# Load daily discharge time series
discharge = pd.read_csv("discharge.csv", index_col=0, parse_dates=True)["discharge"]

# Calculate all hydrological metrics
metrics = calculate_comprehensive_metrics(
    discharge,
    include_bfi=True,          # Include Base Flow Index (slower)
    include_all_modules=True   # Include all metric categories
)

# Access specific metrics
print(f"Mean annual flow: {metrics['magnitude_mean_flow']:.2f} m³/s")
print(f"Base Flow Index: {metrics['baseflow_bfi']:.3f}")
print(f"Q95 (high flow): {metrics['fdc_q95']:.2f} m³/s")
```

**Available modules:**
- `base_flow`: Base Flow Index calculation (Eckhardt filter)
- `flow_duration`: Flow Duration Curve metrics
- `flow_extremes`: High/low flow analysis
- `flow_timing`: Seasonal flow timing metrics
- `flow_variability`: Flow variability and predictability
- `period_based_metrics`: Aggregate metrics by period

### 2. Meteorological Processing (`src/meteo/`)

Aggregate meteorological forcing data over catchments:

```python
from pathlib import Path
import geopandas as gpd
from src.meteo.aggregation import aggregate_watershed

# Load watershed geometry
watersheds = gpd.read_file("data/Geometry/WatershedGeomCAMELS.gpkg")
gauge_geom = watersheds[watersheds["gauge_id"] == "01001"].geometry.iloc[0]

# Aggregate ERA5-Land data over watershed
result = aggregate_watershed(
    geometry=gauge_geom,
    nc_file=Path("data/MeteoData/era5_land_temperature.nc"),
    variable_name="t2m",
    dataset_type="era5-land",
    grid_res=0.10,
    small_threshold=5.0  # km²
)

# Result contains time series of watershed-averaged values
print(result)
```

**Available modules:**
- `aggregation`: Watershed-averaged meteorological variables
- `climate_indices`: Drought indices and climate classification
- `temperature`: Temperature metrics and extremes
- `extremes`: Extreme weather event detection
- `seasonal_stats`: Seasonal climatologies
- `water_balance`: Water balance calculations

### 3. Quality Assessment (`src/quality/`)

Automated and manual quality control for discharge time series:

- `quality_grader`: Rule-based grading of time series quality
- `anomaly_detection`: Spike and flatline detection
- `climatology`: Seasonal envelope checks
- `meteo_response`: Precipitation-discharge consistency checks
- `quality_flags`: Standardized flag definitions
- `data_loader`: Unified loading of gauge time series

### 4. Statistical Analysis (`src/timeseries_stats/`)

Time series analysis tools:

```python
from src.timeseries_stats import analyze_trends, test_homogeneity

# Trend analysis with Mann-Kendall test
trend_results = analyze_trends(discharge)

# Homogeneity testing
homogeneity_results = test_homogeneity(discharge)
```

### 5. Data Processing Scripts (`scripts/`)

#### Data acquisition

| Script | Description |
|--------|-------------|
| `load_era5_land.py` | Download ERA5-Land meteorological forcing via CDS API |
| `gleam_loader.py` | Download GLEAM evapotranspiration data via SFTP |
| `split_gleam_monthly.py` | Split large GLEAM NetCDF files into monthly chunks |

#### Source data parsing

| Script | Description |
|--------|-------------|
| `ParseAisQData.py` | Parse AIS discharge XLS files into per-gauge CSVs |
| `ParseAisHData.py` | Parse AIS water level XLS files into per-gauge CSVs |
| `ParseAisCompound.py` | Merge discharge and water level into compound per-gauge CSVs |

#### Processing and aggregation

| Script | Description |
|--------|-------------|
| `aggregate_watersheds.py` | Aggregate gridded meteorological data over watershed geometries |
| `hydro_atlas_converter.py` | Extract catchment attributes from HydroATLAS |
| `detect_nesting.py` | Identify parent-child watershed nesting relationships |
| `aggregate_signatures.py` | Compute hydrological signatures across all catchments |
| `create_signatures_csv.py` | Calculate per-catchment hydrological signatures and trend statistics |
| `create_signatures_final.py` | Assemble final signatures CSV for the dataset release |
| `GradeCompound.py` | Assess discharge quality against precipitation and assign grades (A–F) |

#### Dataset packaging

| Script | Description |
|--------|-------------|
| `create_hydro_netcdf.py` | Generate CF-compliant NetCDF files for discharge and water level |
| `create_forcing_netcdf.py` | Generate CF-compliant NetCDF for basin-averaged meteorological forcing |
| `package_dataset.py` | Assemble the final Zenodo release package |

#### Example usage

```bash
# Aggregate ERA5-Land variables over watersheds
python scripts/aggregate_watersheds.py \
    --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \
    --input-dir data/MeteoData/ERA5 \
    --output-dir data/MeteoData/Aggregated \
    --dataset-type era5-land \
    --workers 4

# Download ERA5-Land data
python scripts/load_era5_land.py \
    --bbox 40 130 75 170 \
    --variables 2m_temperature total_precipitation \
    --start-year 2000 --end-year 2023 \
    --output data/MeteoData/ERA5
```

### 6. Web Application for Data Quality Review

A FastAPI-based interface for manual review of discharge time series quality:

```bash
cd app
python main.py
# Open browser to http://127.0.0.1:8000
```

**Features:**
- Interactive time series visualization
- Spatial map of gauge locations
- Quality classification (poor/decent, shifted, negatives, zeros)
- Review progress tracking

### 7. Analysis Notebooks

Jupyter notebooks for comprehensive analysis:

- `00_DataDescription.ipynb`: Watershed size distribution and data coverage
- `01_HydroAtlasFinal.ipynb`: Catchment attribute clustering and PCA analysis
- `02_HydrologicalFinal.ipynb`: Hydrological metrics and regime analysis
- `03_ForcingsFinal.ipynb`: Meteorological forcing and water balance analysis
- `04_ZenodoDataset.ipynb`: Dataset packaging for Zenodo release

## Installation

This project uses [pixi](https://pixi.sh) for reproducible dependency management.

```bash
# Clone repository
git clone https://github.com/dmbrmv/camels_ru.git
cd camels_ru

# Install dependencies (Python 3.12+)
pixi install
```

## Data

The dataset itself is not included in this repository. To use the analysis tools:

1. Download the CAMELS-RU dataset from [Zenodo](#) *(link to be added upon publication)*
2. Place or symlink the data directory:
   ```bash
   ln -s /path/to/your/camels_ru_data data
   ```

The `data/` directory is expected to contain subdirectories for geometry, meteorological forcing, discharge observations, and derived attributes. See the notebooks for the expected structure.

## Key Dependencies

- **Core**: Python 3.12+, NumPy, Pandas, SciPy
- **Geospatial**: GeoPandas, Rasterio, Xarray, GDAL
- **Analysis**: Scikit-learn, Statsmodels
- **Visualization**: Matplotlib, Seaborn, Cartopy
- **Performance**: Numba (JIT compilation)
- **Web**: FastAPI, Uvicorn

## Data Coverage

- **Spatial Domain**: Russian Federation river catchments
- **Temporal Coverage**: Multi-decadal (varies by data source)
- **Temporal Resolution**: Daily discharge and meteorological data
- **Gauge Stations**: 450+ stations with quality-controlled discharge data
- **Catchment Attributes**: Topography, land cover, soil, climate, geology

## Methodology Highlights

- **Base Flow Index**: Eckhardt (2005) digital filter with Monte Carlo uncertainty
- **Hydrological Signatures**: 50+ metrics following Addor et al. (2018)
- **Climate Indices**: SPI, SPEI, and standardized drought indicators
- **Spatial Aggregation**: Area-weighted and optimized NetCDF processing
- **Quality Control**: Comprehensive validation and manual review workflows

## Citation

*Citation information will be updated upon publication.*

## Acknowledgments

This work builds upon:

- Newman et al. (2015) — CAMELS US
- Addor et al. (2017) — CAMELS GB
- Addor et al. (2018) — Hydrological signatures
- Lehner et al. (2013) — HydroATLAS

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contact

**Author**: Dmitrii Abramov
**Email**: dmbrmv96@gmail.com
