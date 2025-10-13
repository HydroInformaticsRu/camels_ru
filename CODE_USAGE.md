# CAMELS-RU Code Usage Guide

This document provides comprehensive guidance on using the CAMELS-RU codebase for hydrological analysis, data processing, and visualization.

## Table of Contents

1. [Core Python Modules](#core-python-modules)
2. [Command-Line Scripts](#command-line-scripts)
3. [Web Application](#web-application)
4. [Jupyter Notebooks](#jupyter-notebooks)
5. [Common Workflows](#common-workflows)

---

## Core Python Modules

### Hydrological Analysis (`src/hydro/`)

The hydro package provides comprehensive hydrological metrics calculation.

#### Calculate All Metrics

```python
import pandas as pd
from src.hydro import calculate_comprehensive_metrics

# Load discharge data
discharge = pd.read_csv("discharge.csv", index_col=0, parse_dates=True)["Q"]

# Calculate all metrics
metrics = calculate_comprehensive_metrics(
    discharge,
    include_bfi=True,          # Include Base Flow Index (slow)
    include_all_modules=True   # All metric categories
)

# Results as dictionary
for key, value in metrics.items():
    print(f"{key}: {value:.4f}")
```

#### Individual Metric Modules

```python
from src.hydro import (
    calculate_bfi,
    calculate_fdc_metrics,
    calculate_extreme_metrics,
    calculate_timing_metrics,
    calculate_variability_metrics
)

# Base Flow Index only
bfi = calculate_bfi(discharge, n_iterations=1000)

# Flow Duration Curve metrics
fdc_metrics = calculate_fdc_metrics(discharge)
print(f"Q95: {fdc_metrics['q95']:.2f} m³/s")

# Extreme flow events
extremes = calculate_extreme_metrics(discharge)
print(f"High flow frequency: {extremes['high_freq']:.2f}")

# Flow timing
timing = calculate_timing_metrics(discharge)
print(f"Center of mass: {timing['center_of_mass']:.1f} day")

# Flow variability
variability = calculate_variability_metrics(discharge)
print(f"Coefficient of variation: {variability['cv']:.3f}")
```

#### Period-Based Analysis

```python
from src.hydro import split_by_period, calculate_period_metrics

# Split time series by hydrological year (Oct-Sep)
periods = split_by_period(discharge, period_type='hydrological')

# Calculate metrics for each period
for period_id, period_data in periods.items():
    metrics = calculate_period_metrics(period_data)
    print(f"Period {period_id}: mean flow = {metrics['mean_flow']:.2f}")
```

#### Parallel Processing

```python
from src.hydro.parallel_metrics import calculate_metrics_parallel
import geopandas as gpd

# Load multiple gauge stations
gauges = gpd.read_file("data/Geometry/GaugeGeomCAMELS.gpkg")
gauge_ids = gauges["gauge_id"].tolist()

# Process in parallel
results = calculate_metrics_parallel(
    gauge_ids=gauge_ids,
    data_dir="data/HydroFiles",
    n_workers=4,
    include_bfi=False  # Skip BFI for speed
)

# Results as DataFrame
import pandas as pd
results_df = pd.DataFrame(results).T
results_df.to_csv("hydrological_metrics.csv")
```

---

### Meteorological Processing (`src/meteo/`)

#### Watershed Aggregation

```python
from pathlib import Path
import geopandas as gpd
from src.meteo.aggregation import aggregate_watershed

# Load watershed geometry
watersheds = gpd.read_file("data/Geometry/WatershedGeomCAMELS.gpkg")
gauge_id = "01001"
geometry = watersheds[watersheds["gauge_id"] == gauge_id].geometry.iloc[0]

# Aggregate NetCDF data over watershed
nc_file = Path("data/MeteoData/ERA5/temperature_2m.nc")
result = aggregate_watershed(
    geometry=geometry,
    nc_file=nc_file,
    variable_name="t2m",
    dataset_type="era5-land",
    grid_res=0.10,
    small_threshold=5.0  # km²
)

# Result is a pandas Series with time index
print(result.head())
result.to_csv(f"temperature_{gauge_id}.csv")
```

#### Climate Indices

```python
from src.meteo import calculate_drought_indices, calculate_temperature_metrics

# Calculate drought indices (SPI, SPEI)
precipitation = pd.read_csv("precip.csv", index_col=0, parse_dates=True)["P"]
temperature = pd.read_csv("temp.csv", index_col=0, parse_dates=True)["T"]

drought_indices = calculate_drought_indices(precipitation, temperature)

# Temperature metrics
temp_metrics = calculate_temperature_metrics(temperature)
print(f"Mean annual temp: {temp_metrics['mean_annual']:.2f}°C")
```

#### Extreme Events

```python
from src.meteo import calculate_extreme_events

# Detect extreme precipitation events
precip = pd.read_csv("precip.csv", index_col=0, parse_dates=True)["P"]

extremes = calculate_extreme_events(
    precip,
    threshold_percentile=95,  # 95th percentile
    event_type="precipitation"
)

print(f"Number of extreme events: {extremes['n_events']}")
print(f"Max event magnitude: {extremes['max_magnitude']:.2f} mm")
```

---

### Data Processing (`src/data_processing/`)

#### Geometric Operations

```python
from src.data_processing.geom_functions import (
    polygon_area,
    create_gdf,
    gauge_buffer_creator
)
from shapely.geometry import Point

# Calculate polygon area in km²
area_km2 = polygon_area(polygon_geom)

# Create buffer around gauge
point = Point(55.5, 37.5)  # lat, lon
buffer_gdf = gauge_buffer_creator(
    point,
    buffer_km=50,
    crs_epsg=4326
)
```

#### NetCDF Processing

```python
from src.data_processing.nc_proc import nc_by_extent
from pathlib import Path

# Extract data within bounding box
nc_file = Path("data/MeteoData/ERA5/temperature.nc")
bbox = (50, 100, 60, 110)  # min_lat, min_lon, max_lat, max_lon

extracted_data = nc_by_extent(
    nc_file,
    extent=bbox,
    variable_name="t2m"
)

# Save subset
extracted_data.to_netcdf("temperature_subset.nc")
```

---

### Time Series Statistics (`src/timeseries_stats/`)

```python
from src.timeseries_stats import (
    analyze_trends,
    test_homogeneity,
    detect_change_points
)

# Trend analysis
trends = analyze_trends(
    discharge,
    method="mann-kendall",
    alpha=0.05
)
print(f"Trend detected: {trends['significant']}")
print(f"Sen's slope: {trends['slope']:.4f}")

# Homogeneity testing
homogeneity = test_homogeneity(
    discharge,
    methods=["pettitt", "snht"]
)

# Change point detection
change_points = detect_change_points(
    discharge,
    method="pettitt"
)
```

---

## Command-Line Scripts

### 1. Aggregate Watersheds (`scripts/aggregate_watersheds.py`)

Aggregate meteorological data over catchments from NetCDF files.

```bash
python scripts/aggregate_watersheds.py \
    --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \
    --input-dir data/MeteoData/ERA5 \
    --output-dir data/MeteoData/Aggregated \
    --dataset-type era5-land \
    --pattern "*.nc" \
    --gauge-ids 01001 01002 01003 \
    --grid-res 0.10 \
    --small-threshold 5.0 \
    --workers 4
```

**Options:**

- `--watersheds`: Path to GeoPackage with watershed geometries
- `--input-dir`: Directory containing input NetCDF files
- `--output-dir`: Output directory for aggregated CSV files
- `--dataset-type`: Dataset type (era5-land, gleam, gpcp, etc.)
- `--pattern`: Glob pattern for input files (default: `*.nc`)
- `--gauge-ids`: Process specific gauge IDs (optional)
- `--grid-res`: Grid resolution in degrees (default: 0.10)
- `--small-threshold`: Small watershed threshold in km² (default: 5.0)
- `--workers`: Number of parallel workers (default: 4)

**Output:**

One CSV file per gauge per NetCDF file in the output directory.

---

### 2. GLEAM Data Loader (`scripts/gleam_loader.py`)

Download GLEAM evapotranspiration data via SFTP.

```bash
export GLEAM_SFTP_PASSWORD="your_password"

python scripts/gleam_loader.py \
    --version v4.2a \
    --freq daily \
    --years "2008:2023" \
    --vars E Ei Ep Et Ew S SMsurf SMroot \
    --dest data/MeteoData/GLEAM \
    --username gleamuser \
    --workers 4
```

**Options:**

- `--version`: GLEAM version (e.g., v4.2a)
- `--freq`: Temporal frequency (daily or monthly)
- `--years`: Year range (e.g., "2008:2023" or "2008,2010,2012-2014")
- `--vars`: Variables to download (E, Ei, Ep, Et, Ew, S, SMsurf, SMroot)
- `--dest`: Destination directory
- `--username`: SFTP username (default: gleamuser)
- `--password`: SFTP password (or set via environment variable)
- `--workers`: Number of parallel download workers
- `--dry-run`: Show what would be downloaded without downloading
- `--list-only`: List available files and exit

**Available GLEAM Variables:**

- `E`: Actual evapotranspiration
- `Ei`: Interception evaporation
- `Ep`: Potential evapotranspiration
- `Et`: Transpiration
- `Ew`: Open-water evaporation
- `S`: Snow sublimation
- `SMsurf`: Surface soil moisture
- `SMroot`: Root-zone soil moisture

---

### 3. ERA5-Land Loader (`scripts/load_era5_land.py`)

Download ERA5-Land data from Copernicus Climate Data Store.

```bash
python scripts/load_era5_land.py \
    --bbox 40 130 75 170 \
    --variables 2m_temperature total_precipitation \
    --start-year 2000 \
    --end-year 2023 \
    --output data/MeteoData/ERA5
```

**Options:**

- `--bbox`: Bounding box (min_lat min_lon max_lat max_lon)
- `--variables`: ERA5-Land variables to download
- `--start-year`: Start year
- `--end-year`: End year
- `--output`: Output directory

**Common ERA5-Land Variables:**

- `2m_temperature`: 2-meter air temperature
- `total_precipitation`: Total precipitation
- `surface_pressure`: Surface pressure
- `10m_u_component_of_wind`: 10m U wind component
- `10m_v_component_of_wind`: 10m V wind component
- `surface_solar_radiation_downwards`: Downward solar radiation

---

### 4. HydroATLAS Converter (`scripts/hydro_atlas_converter.py`)

Extract catchment attributes from HydroATLAS database.

```bash
python scripts/hydro_atlas_converter.py
```

**Configuration:**

Edit the script to set:

- `HYDRO_ATLAS_GDB`: Path to HydroATLAS geodatabase
- `WATERSHED_FILE`: Path to watershed geometries
- `GAGES_FILE`: Path to gauge geometries
- `OUTPUT_CSV`: Output CSV file path

**Output:**

CSV file with HydroATLAS attributes for each catchment.

---

## Web Application

### Data Quality Review Application

Interactive web interface for manual review of discharge time series.

#### Start the Application

```bash
cd app
python main.py
```

#### Access the Interface

Open browser to `http://127.0.0.1:8000`

#### Features

1. **Time Series Visualization**: Interactive plots of discharge data
2. **Spatial Map**: Folium map showing gauge locations
3. **Quality Classification**:
   - **Poor/Decent**: Overall quality assessment
   - **Shifted**: Time series has temporal shift
   - **Negatives**: Contains negative values
   - **Zeros**: Contains suspicious zeros
4. **Progress Tracking**: Review status and counts
5. **Automated Classification**: Series automatically classified as empty/partial/full

#### Output Structure

```
update/
├── full/
│   ├── poor/
│   └── decent/
├── partial/
│   ├── poor/
│   └── decent/
├── freezing/
│   ├── poor/
│   └── decent/
├── negatives/
│   ├── poor/
│   └── decent/
├── shifted/
└── logs/
```

#### Configuration

Edit `app/main.py`:

```python
DATA_DIR = BASE_DIR / "data"  # CSV files to review
UPDATE_DIR = BASE_DIR / "update"  # Output directory
METRICS_PATH = BASE_DIR / "metrics.csv"  # Optional metrics file
```

---

## Jupyter Notebooks

### HydrologicalFinal.ipynb

Complete hydrological analysis workflow:

1. Load discharge data
2. Calculate comprehensive metrics
3. Perform clustering analysis
4. Generate visualizations
5. Export results

### ForcingsFinal.ipynb

Meteorological forcing analysis:

1. Load meteorological data
2. Calculate climate indices
3. Trend analysis
4. Correlation with discharge
5. Generate plots

### HydroAtlasFinal.ipynb

Catchment attribute analysis:

1. Load HydroATLAS attributes
2. Clustering by physiographic characteristics
3. Relationship with hydrological signatures
4. Statistical analysis

### PaperBook.ipynb

Paper figure generation:

1. Load all results
2. Generate publication-ready figures
3. Statistical summaries
4. Export to LaTeX tables

---

## Common Workflows

### Workflow 1: Calculate Metrics for All Gauges

```python
import pandas as pd
import geopandas as gpd
from pathlib import Path
from src.hydro import calculate_comprehensive_metrics

# Load gauge list
gauges = gpd.read_file("data/Geometry/GaugeGeomCAMELS.gpkg")

results = {}
for gauge_id in gauges["gauge_id"]:
    # Load discharge data
    file_path = Path(f"data/HydroFiles/{gauge_id}.csv")
    if not file_path.exists():
        continue
    
    discharge = pd.read_csv(file_path, index_col=0, parse_dates=True)["Q"]
    
    # Calculate metrics
    metrics = calculate_comprehensive_metrics(discharge, include_bfi=False)
    results[gauge_id] = metrics

# Save results
results_df = pd.DataFrame(results).T
results_df.to_csv("results/hydrological_metrics_all.csv")
```

### Workflow 2: Complete Meteorological Processing

```bash
# 1. Download ERA5-Land data
python scripts/load_era5_land.py \
    --bbox 40 130 75 170 \
    --variables 2m_temperature total_precipitation \
    --start-year 2000 --end-year 2023 \
    --output data/MeteoData/ERA5

# 2. Aggregate over watersheds
python scripts/aggregate_watersheds.py \
    --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \
    --input-dir data/MeteoData/ERA5 \
    --output-dir data/MeteoData/Aggregated \
    --dataset-type era5-land \
    --workers 4

# 3. Download GLEAM data
python scripts/gleam_loader.py \
    --version v4.2a --freq daily \
    --years "2000:2023" \
    --vars E Ep \
    --dest data/MeteoData/GLEAM

# 4. Aggregate GLEAM data
python scripts/aggregate_watersheds.py \
    --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \
    --input-dir data/MeteoData/GLEAM \
    --output-dir data/MeteoData/Aggregated \
    --dataset-type gleam \
    --workers 4
```

### Workflow 3: Combined Analysis

```python
import pandas as pd
from src.hydro import calculate_comprehensive_metrics
from src.timeseries_stats import analyze_trends
from src.meteo import calculate_drought_indices

gauge_id = "01001"

# Load data
discharge = pd.read_csv(f"data/HydroFiles/{gauge_id}.csv", 
                       index_col=0, parse_dates=True)["Q"]
precip = pd.read_csv(f"data/MeteoData/Aggregated/{gauge_id}_precip.csv",
                    index_col=0, parse_dates=True)["P"]

# Hydrological metrics
hydro_metrics = calculate_comprehensive_metrics(discharge)

# Trend analysis
trends = analyze_trends(discharge)

# Drought indices
drought = calculate_drought_indices(precip, temperature=None)

# Combine results
combined = {
    **{f"hydro_{k}": v for k, v in hydro_metrics.items()},
    **{f"trend_{k}": v for k, v in trends.items()},
    **{f"drought_{k}": v for k, v in drought.items()}
}

# Save
pd.Series(combined).to_csv(f"results/{gauge_id}_complete_analysis.csv")
```

---

## Logging

All modules use consistent logging:

```python
from src.utils.logger import setup_logger

# Create logger
logger = setup_logger(
    function_name="my_analysis",
    log_file="logs/analysis.log",
    log_level="INFO"
)

# Use logger
logger.info("Starting analysis")
logger.warning("Missing data detected")
logger.error("Processing failed")
```

**Features:**

- Emoji-enhanced console output
- Rotating file handlers
- Colored output (auto-detected TTY)
- Environment variable overrides (`camels_ru_LOG_LEVEL`)

---

## Best Practices

1. **Data Paths**: Use absolute paths or pathlib.Path objects
2. **Parallelization**: Use workers=4 for most operations
3. **Memory**: Process large datasets in chunks
4. **Logging**: Always use setup_logger for consistency
5. **Testing**: Test on small subset before processing all data
6. **Documentation**: Add docstrings for new functions

---

For more information, see:

- [Documentation Index](../docs/index.md)
- [Methodology](../docs/methodology/)
- [API Reference](../docs/complete_reference.md)
