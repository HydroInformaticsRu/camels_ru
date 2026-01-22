# CAMELS-RU: A Hydrological Dataset for Russia

## Overview

CAMELS-RU is a comprehensive hydrological dataset project for Russia providing catchment attributes, meteorological forcing data, and hydrological analysis tools. This project creates a CAMELS-type dataset tailored for Russian river basins, following standards established by Newman et al. (2015) and Addor et al. (2017).

## Project Structure

```
camels_ru/
├── src/                      # Core analysis modules
│   ├── hydro/               # Hydrological metrics and signatures
│   ├── meteo/               # Meteorological data processing and analysis
│   ├── data_processing/     # Geospatial and NetCDF utilities
│   ├── timeseries_stats/    # Trend analysis and statistical tests
│   ├── plots/               # Visualization functions
│   ├── static/              # HydroATLAS and clustering tools
│   └── utils/               # Logging and utilities
├── scripts/                 # Command-line data processing tools
│   ├── aggregate_watersheds.py  # Aggregate meteorological data
│   ├── gleam_loader.py          # GLEAM data downloader
│   ├── load_era5_land.py        # ERA5-Land data retrieval
│   └── hydro_atlas_converter.py # HydroATLAS attribute extraction
├── app/                     # Web interface for data quality review
├── notebooks/               # Jupyter analysis notebooks
├── docs/                    # Documentation
└── data/                    # Data storage (not in repository)
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

### 3. Statistical Analysis (`src/timeseries_stats/`)

Time series analysis tools:

```python
from src.timeseries_stats import analyze_trends, test_homogeneity

# Trend analysis with Mann-Kendall test
trend_results = analyze_trends(discharge)

# Homogeneity testing
homogeneity_results = test_homogeneity(discharge)
```

### 4. Data Processing Scripts

#### Aggregate Meteorological Data

```bash
# Aggregate all ERA5-Land variables for multiple watersheds
python scripts/aggregate_watersheds.py \
    --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \
    --input-dir data/MeteoData/ERA5 \
    --output-dir data/MeteoData/Aggregated \
    --dataset-type era5-land \
    --workers 4
```

#### Download GLEAM Data

```bash
# Download GLEAM evapotranspiration data
python scripts/gleam_loader.py \
    --version v4.2a \
    --freq daily \
    --years "2008:2023" \
    --vars E Ei Ep Et Ew S SMsurf SMroot \
    --dest data/MeteoData/GLEAM \
    --username gleamuser \
    --password $GLEAM_SFTP_PASSWORD
```

#### Download ERA5-Land Data

```bash
# Download ERA5-Land meteorological forcing
python scripts/load_era5_land.py \
    --bbox 40 130 75 170 \
    --variables 2m_temperature total_precipitation \
    --start-year 2000 \
    --end-year 2023 \
    --output data/MeteoData/ERA5
```

#### Extract HydroATLAS Attributes

```bash
# Extract catchment attributes from HydroATLAS
python scripts/hydro_atlas_converter.py
```

### 5. Web Application for Data Quality Review

A FastAPI-based interface for manual review of discharge time series quality:

```bash
# Start the review application
cd app
python main.py

# Open browser to http://127.0.0.1:8000
```

**Features:**
- Interactive time series visualization
- Spatial map of gauge locations
- Quality classification (poor/decent, shifted, negatives, zeros)
- Review progress tracking
- Automated series classification

### 6. Analysis Notebooks

Jupyter notebooks for comprehensive analysis:

- `HydrologicalFinal.ipynb`: Complete hydrological analysis workflow
- `ForcingsFinal.ipynb`: Meteorological forcing analysis
- `HydroAtlasFinal.ipynb`: Catchment attribute analysis
- `PaperBook.ipynb`: Paper figure generation

## Installation

```bash
# Clone repository
git clone <repository-url>
cd camels_ru

# Install dependencies (Python 3.12+)
pip install -r requirements.txt

# Or use pip install with extras
pip install -e ".[dev]"
```

## Key Dependencies

- **Core**: Python 3.12+, NumPy, Pandas, SciPy
- **Geospatial**: GeoPandas, Rasterio, Xarray, GDAL
- **Analysis**: Scikit-learn, Statsmodels
- **Visualization**: Matplotlib, Cartopy, Folium
- **Performance**: Numba (JIT compilation)
- **Web**: FastAPI, Uvicorn

## Documentation

- **[Documentation Index](docs/index.md)**: Central documentation hub
- **[Methodology](docs/methodology/)**: Scientific methods and formulations
- **[Usage Guides](docs/usage_guides/)**: Practical how-to guides
- **[Analysis Results](docs/analysis_results/)**: Dataset analysis summaries
- **[API Reference](docs/complete_reference.md)**: Complete function reference

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

## Code Quality

- **Type Hints**: Full type annotations throughout
- **Linting**: Ruff-compliant (PEP 8 standards)
- **Formatting**: Consistent code style with 79-char line limit
- **Documentation**: Google-style docstrings
- **Logging**: Comprehensive logging with emoji-enhanced console output

## Citation

*Citation information will be updated upon publication*

## Acknowledgments

This work builds upon:

- Newman et al. (2015) - CAMELS US
- Addor et al. (2017) - CAMELS GB
- Addor et al. (2018) - Hydrological signatures
- Lehner et al. (2013) - HydroATLAS

## License

MIT License - see LICENSE file for details

## Contact

**Author**: Dmitrii Abramov  
**Email**: dmbrmv96@gmail.com  
**Project**: CAMELS-RU Hydrological Dataset
