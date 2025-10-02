# CAMELS-RU: A Comprehensive Hydrological Dataset for Russia

## Overview

CAMELS-RU is a large-scale hydrological dataset for Russia that provides comprehensive catchment attributes and meteorological forcing data. This project aims to create a CAMELS-type dataset following the standards established by Newman et al. (2015) and Addor et al. (2017), specifically tailored for Russian river basins.

## Project Scope

### Data Coverage

- **Spatial Domain**: Russian Federation river catchments
- **Temporal Domain**: Multi-decadal time series (specific periods vary by data source)
- **Catchment Scale**: From small headwater basins to large river systems
- **Resolution**: Daily meteorological forcing and discharge observations

### Dataset Components

1. **Hydrological Data**
   - Daily discharge observations from gauge stations
   - Comprehensive hydrological indices and signatures
   - Base flow separation and analysis
   - Flow duration curves and extremes

2. **Meteorological Forcing**
   - Daily precipitation, temperature (min/max/mean)
   - Potential evapotranspiration estimates
   - Climate indices and drought indicators
   - Extreme weather events characterization

3. **Catchment Attributes**
   - Topographic characteristics (elevation, slope, aspect)
   - Land cover and land use classifications
   - Soil properties and geology
   - Climate classifications and aridity indices

## Methodology

The project implements scientifically rigorous methods for:

- **Hydrological Signature Extraction**: Following Addor et al. (2018) guidelines
- **Base Flow Index (BFI)**: Eckhardt (2005) digital filter implementation with 1000 Monte Carlo realizations
- **Climate Indices**: Standardized calculations for SPI, SPEI, and drought indicators
- **Quality Control**: Comprehensive data validation and gap-filling procedures
- **Spatial Analysis**: GIS-based catchment delineation and attribute extraction

## Key Features

### 🔧 Robust Processing Pipeline

- Modular architecture with separate packages for hydrology, meteorology, and statistics
- Comprehensive error handling and logging system
- Type-hinted Python codebase following PEP 8 standards
- Reproducible analysis with controlled random seeds

### 📊 Advanced Analytics

- **Hydrological Metrics**: 50+ signatures including flow timing, magnitude, duration, and variability
- **Climate Analysis**: Temperature extremes, precipitation patterns, and drought indices
- **Statistical Assessment**: Trend analysis, change point detection, and time series diagnostics
- **Visualization Tools**: Publication-ready plots and interactive analysis notebooks

### 🌍 Geospatial Integration

- HydroATLAS integration for physiographic attributes
- DEM-based terrain analysis
- Land cover classification from satellite imagery
- Soil and geological data incorporation

## Quick Start

```python
import pandas as pd
from src.hydro_metrics import hydro_job
from src.processing import split_by_hydro_year

# Load discharge data
discharge = pd.read_csv("discharge.csv", index_col=0, parse_dates=True)

# Split by hydrological year
hydro_years = split_by_hydro_year(discharge['flow'])

# Calculate hydrological metrics for each year
for year, data in hydro_years.items():
    if len(data) > 300:  # Ensure sufficient data
        calendar_data = data  # Adjust as needed
        hydro_job(data, calendar_data)
```

## Documentation Structure

- **[`docs/methodology/`](docs/methodology/)**: Detailed mathematical formulations and algorithms
- **[`docs/api/`](docs/api/)**: Complete API reference for all modules
- **[`docs/data_sources/`](docs/data_sources/)**: Data acquisition and processing pipelines
- **[`notebooks/`](notebooks/)**: Interactive Jupyter notebooks with usage examples

## Dependencies

- **Core**: Python 3.12+, NumPy, Pandas, SciPy
- **Geospatial**: GeoPandas, Rasterio, Xarray
- **Analysis**: Scikit-learn, Statsmodels
- **Visualization**: Matplotlib, Seaborn
- **Performance**: Numba (JIT compilation for critical algorithms)

## Data Availability

The complete CAMELS-RU dataset will be made publicly available through:

- Zenodo repository with DOI
- HydroShare platform
- National hydrological data portals

## Contributing

This project follows scientific software development best practices:

- All contributions must include comprehensive tests
- Code must pass Ruff linting (configured in `pyproject.toml`)
- Documentation must be updated for new features
- Scientific methods must include peer-reviewed references

## Citation

*Citation information will be updated upon publication*

## Acknowledgments

This work builds upon the foundational CAMELS datasets and methodologies developed by:

- Newman et al. (2015) - CAMELS US
- Addor et al. (2017) - CAMELS GB  
- Addor et al. (2018) - Hydrological signatures
- Kratzert et al. (2022) - CARAVAN

## License

This project is licensed under [specify license] - see LICENSE file for details.

---

**Contact**: [dmbrmv96@gmail.com]  
**Project Repository**: [Repository URL]  
**Documentation**: [Documentation URL]
