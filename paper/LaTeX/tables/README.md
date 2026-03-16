# CAMELS-RU LaTeX Tables - Overview

This directory contains professional LaTeX tables for the CAMELS-RU manuscript, generated from analysis results.

## Available Tables

### 1. Data Coverage and Characteristics

#### `data_coverage_summary.tex`
- **Label**: `tab:data_coverage`
- **Content**: Summary of hydrological data coverage (discharge and water level gauges)
- **Use in**: Section 2 (Study Area) or Section 3 (Data Sources)
- **Key stats**: 
  - 2183 discharge gauges, 2687 water level gauges
  - Quality breakdown (decent vs. poor)
  - Co-located measurements

#### `watershed_size_distribution.tex`
- **Label**: `tab:watershed_size`
- **Content**: Distribution of catchments by size category
- **Use in**: Section 2 (Study Area) or Section 3 (Data Sources)
- **Key stats**: 
  - 6 size categories from <100 km² to >200,000 km²
  - Median area: 2923 km²

### 2. Meteorological Forcing

#### `precipitation_comparison.tex`
- **Label**: `tab:precipitation_comparison`
- **Content**: Comparison of three precipitation datasets (ERA5-Land, MSWEP, GPCP)
- **Use in**: Section 3 (Data Sources) or Section 6 (Technical Validation)
- **Key stats**: 
  - Mean annual precipitation for each dataset
  - Correlation with discharge

#### `precipitation_trends.tex`
- **Label**: `tab:precipitation_trends`
- **Content**: Long-term precipitation trend analysis
- **Use in**: Section 6b (Trend Analysis)
- **Key stats**: 
  - Mann-Kendall trend test results
  - Percentage of gauges with significant trends

### 3. Static Attributes and Signatures

#### `hydroatlas_attributes.tex`
- **Label**: `tab:hydroatlas_attributes`
- **Content**: Complete list of 22 HydroATLAS attributes
- **Use in**: Section 4 (Attributes and Signatures)
- **Categories**: 
  - Topography & Climate (4 attributes)
  - Cryosphere (3)
  - Land Cover (6)
  - Soil Properties (3)
  - Hydrogeology (2)
  - Flood Regulation (2)
  - Socioeconomic (2)

#### `hydro_signatures.tex`
- **Label**: `tab:hydro_signatures`
- **Content**: Hydrological signatures calculated for catchments
- **Use in**: Section 4 (Attributes and Signatures)
- **Categories**: 
  - Flow Magnitude (5 signatures)
  - Flow Timing (3)
  - Flow Duration (4)
  - Baseflow & Recession (3)
  - Water Balance (3)

### 4. Clustering Analysis

#### `geo_clusters_summary.tex`
- **Label**: `tab:geo_clusters`
- **Content**: Summary of 15 geophysical catchment clusters
- **Use in**: Section 5 (Clustering and Regional Analysis)
- **Key metrics**: 
  - Number of gauges per cluster
  - Mean area, elevation, precipitation
  - Forest, crop, and permafrost coverage

## Integration Instructions

1. **Add to main document**: Use `\input{tables/filename}` in the appropriate section
2. **Reference in text**: Use `Table~\ref{tab:label}` to reference
3. **Package requirements**: Ensure main.tex includes:
   - `\usepackage{booktabs}` (for professional table formatting)
   - `\usepackage{threeparttable}` (for table notes)
   - `\usepackage{multirow}` (for multi-row cells)

## Example Integration

```latex
% In section 03_data_sources_methods.tex
The dataset comprises comprehensive hydrological measurements across \ntotal watersheds 
(Table~\ref{tab:data_coverage}), with catchment sizes ranging from headwater streams to 
major rivers (Table~\ref{tab:watershed_size}).

\input{tables/data_coverage_summary}
\input{tables/watershed_size_distribution}
```

See `README_TABLE_INTEGRATION.tex` for complete integration examples.

## Data Sources

All tables are generated from CSV files in:
- `paper/analysis_results/data_representation/tables/`
- `paper/analysis_results/forcing_representation/tables/`
- `paper/analysis_results/geophysical_representation/tables/`

## Notes

- All tables use IEEE Transactions style formatting
- Table notes provide additional context and methodology details
- Macros from `macros.tex` are used where applicable for consistency
- Some tables use `\begin{table*}` for two-column width (geo_clusters, hydroatlas_attributes, precipitation_trends)
