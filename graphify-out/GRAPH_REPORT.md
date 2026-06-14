# Graph Report - camels_ru  (2026-06-14)

## Corpus Check
- 98 files · ~2,563,913 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1742 nodes · 3231 edges · 89 communities (85 shown, 4 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 69 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `23dd02ee`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]

## God Nodes (most connected - your core abstractions)
1. `QualityFlag` - 41 edges
2. `assess_gauge_quality()` - 27 edges
3. `FlowVariability` - 23 edges
4. `main()` - 22 edges
5. `Path` - 20 edges
6. `FlagSeverity` - 19 edges
7. `TrendAnalysis` - 19 edges
8. `process_section()` - 17 edges
9. `calculate_comprehensive_metrics()` - 17 edges
10. `calculate_seasonal_statistics()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `process_single_watershed()` --calls--> `poly_from_multipoly()`  [INFERRED]
  notebooks/WatershedsMP.py → src/data_processing/geom_functions.py
- `process_single_watershed()` --calls--> `polygon_area()`  [INFERRED]
  notebooks/WatershedsMP.py → src/data_processing/geom_functions.py
- `run_temperature_aware_qc()` --calls--> `assess_gauge_quality()`  [INFERRED]
  scripts/compare_temperature_aware_qc.py → src/quality/quality_grader.py
- `int` --uses--> `FlowVariability`  [INFERRED]
  scripts/create_paper_signatures.py → src/hydro/flow_variability.py
- `float` --uses--> `FlowVariability`  [INFERRED]
  scripts/create_paper_signatures.py → src/hydro/flow_variability.py

## Import Cycles
- 1-file cycle: `src/meteo/era5_land_loader.py -> src/meteo/era5_land_loader.py`

## Communities (89 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (52): classify_series(), Classify a CSV time series based on NaN distribution and coverage., index(), str, Render the index page for CSV review.      Picks the next unreviewed file by def, Pydantic model for the review form payload., Handle the review submission and persist the classification decision.      Rules, review() (+44 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (52): create_mosaic(), create_tif_get_area(), flood_extent_tiles(), gdal_extent_clipper(), get_point_height_from_dem(), Clip and reproject a GeoTIFF file to a desired extent and EPSG code.      This f, Return the paths for .tiff files of elevation and flow direction in a given fold, Generate a VRT mosaic from a collection of GeoTIFF tiles.      Args:         fil (+44 more)

### Community 2 - "Community 2"
Cohesion: 0.17
Nodes (26): Axes, _add_graticule(), _auto_bins(), categorical_map(), continuous_multiplot(), get_russia_projection(), _hide_frame(), Projected plotting for CAMELS-RU manuscript figures.  Spatial plotting using Alb (+18 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (48): ais_merger(), _clean_cell(), _df_from_observations(), discharge_to_csv(), _interpolate_dots(), level_to_csv(), _process_year_block(), AIS GMVO data parsing utilities.  Parses discharge and water level exports from (+40 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (40): calculate_recession_constant(), calculate_trend_statistics(), load_discharge_series(), load_precipitation_series(), main(), process_single_gauge(), float, int (+32 more)

### Community 5 - "Community 5"
Cohesion: 0.04
Nodes (46): 1.1 Large-Sample Hydrology and the CAMELS Framework, 1.2 The Russian Federation: An Unrepresented Region, 1.3 Objectives, 1 Introduction, 2 Study Area, 3.1.1 Data Source and Selection Criteria, 3.1.2 Quality Control, 3.1.3 Water Level Processing (+38 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (31): calculate_flow_stability_index(), calculate_variability_metrics(), FlowVariability, Calculate autocorrelation-based variability metrics.          Returns:, Calculate flashiness index and related metrics.          Returns:             Di, Calculate seasonal variability metrics.          Returns:             Dictionary, Analysis of flow variability at multiple temporal scales.      This class provid, Calculate inter-annual variability metrics.          Returns:             Dictio (+23 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (28): Client, datetime, download_era(), Era5LandDownloader, Module to download ERA5-Land data from the Copernicus Data Store.  Contains func, Remove an incomplete or corrupted file.          Args:             file_path: Pa, Validate and convert input dates to datetime objects.          Args:, Validate and return meteorological variables list.          Args:             va (+20 more)

### Community 8 - "Community 8"
Cohesion: 0.10
Nodes (23): Any, bool, int, Logger, LoggerAdapter, LogRecord, Path, str (+15 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (52): apply_citation_map(), apply_macros(), _ascii_fold(), demote_section_heading(), _extract_braced_field(), insert_section_labels(), main(), parse_bib_authors() (+44 more)

### Community 10 - "Community 10"
Cohesion: 0.11
Nodes (24): calculate_drought_indices(), DroughtIndices, Climate and drought indices for meteorological analysis.  This module provides c, Fit gamma distribution and calculate SPI., Fit Pearson Type III distribution and calculate SPI., Calculate Standardized Precipitation Evapotranspiration Index (SPEI).          A, Calculate various drought and climate indices., Calculate PET using Thornthwaite method (simplified). (+16 more)

### Community 11 - "Community 11"
Cohesion: 0.11
Nodes (24): calculate_seasonal_statistics(), Seasonal meteorological statistics analysis.  This module provides tools for ana, Calculate monthly climatological means.          Args:             reference_per, Calculate seasonal anomalies relative to climatology.          Args:, Calculate statistics describing the annual cycle.          Returns:, Seasonal statistics analysis for meteorological data., Calculate timing of annual peak using harmonic analysis., Initialize seasonal statistics analysis.          Args:             data: Meteor (+16 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (35): _load_forcing_notes(), _load_gauge_zero_heights(), main(), package_attributes(), package_boundaries(), package_discharge(), package_forcing(), package_readme() (+27 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (22): GradeType, GradedDischargeLoader, load_graded_discharge(), Data loader utilities for grade-filtered discharge data.  This module provides e, Get gauge IDs with high quality (A or B grade).          Returns:             Li, Load data for a single gauge.          Args:             gauge_id: Gauge identif, Load data for all gauges matching specified grades.          Args:             g, Load discharge time series for a gauge.          Args:             gauge_id: Gau (+14 more)

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (21): calculate_extreme_events(), ExtremeEvents, Extreme meteorological events analysis.  This module provides tools for identify, Analyze periods of extreme conditions., Identify heat wave events.          Args:             temperature_threshold: Min, Analysis of extreme meteorological events., Identify cold spell events.          Args:             temperature_threshold: Ma, Initialize extreme events analysis.          Args:             data: Meteorologi (+13 more)

### Community 15 - "Community 15"
Cohesion: 0.11
Nodes (30): build_zenodo_tree(), copy_attributes(), copy_discharge(), copy_meteo(), main(), merge_roi_gauges(), merge_roi_watersheds(), parse_area_value() (+22 more)

### Community 16 - "Community 16"
Cohesion: 0.14
Nodes (30): build_include_globs(), connect_sftp(), download_file(), ensure_parent_dir(), filter_paths(), human_bytes(), inspect_local_file(), _listdir_attr_recursive() (+22 more)

### Community 17 - "Community 17"
Cohesion: 0.11
Nodes (22): Meteorological analysis package for CAMELS-RU dataset.  This package provides co, calculate_temperature_metrics(), Temperature analysis for meteorological time series.  This module provides compr, Calculate seasonal temperature statistics.          Returns:             DataFra, Identify extreme temperature events.          Args:             cold_threshold:, Comprehensive temperature analysis for meteorological time series., Calculate consecutive days meeting a condition., Calculate growing and heating degree days.          Args:             base_temp: (+14 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (25): _backward_pass(), BaseFlowSeparation, _bfi_ensemble(), calculate_bfi(), _first_pass(), _forward_pass(), Base flow separation methods for hydrological analysis.  This module provides di, Reflect discharge series to handle boundary effects.      Args:         discharg (+17 more)

### Community 19 - "Community 19"
Cohesion: 0.14
Nodes (19): calculate_comprehensive_metrics(), calculate_regime_classification_metrics(), HydrologicalIndices, Calculate duration-related flow indices.          Returns:             Dictionar, Calculate timing-related flow indices.          Returns:             Dictionary, Calculate rate of change indices.          Returns:             Dictionary of ra, Count number of discrete pulses (events).          Args:             condition_s, Get durations of consecutive events.          Args:             condition_series (+11 more)

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (20): Any, bool, DataArray, float, int, Series, str, HomogeneityTests (+12 more)

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (27): aggregate_large_watershed(), aggregate_small_watershed(), aggregate_watershed(), compute_fractional_weights(), _detect_time_coord(), _get_or_compute_weights(), get_unit_conversion(), _iter_aggregatable_data_vars() (+19 more)

### Community 22 - "Community 22"
Cohesion: 0.12
Nodes (26): CAMELS-RU catchment attributes and clustering for the HESS manuscript.  Produces, DataFrame, float, Index, int, Series, str, categorize_catchment_size() (+18 more)

### Community 23 - "Community 23"
Cohesion: 0.16
Nodes (18): Any, DataArray, float, int, Series, str, ChangePointDetection, detect_change_points() (+10 more)

### Community 24 - "Community 24"
Cohesion: 0.14
Nodes (18): calculate_fdc_metrics(), calculate_flow_regime_classification(), FlowDurationCurve, Get FDC curve data for plotting.          Returns:             DataFrame with ex, Calculate comprehensive FDC-based metrics.      Args:         discharge: Dischar, Classify flow regime based on FDC characteristics.      Args:         discharge:, Flow Duration Curve analysis and metrics calculation.      This class provides c, Initialize FDC with discharge data.          Args:             discharge: Discha (+10 more)

### Community 25 - "Community 25"
Cohesion: 0.13
Nodes (19): calculate_flow_regime_stability(), calculate_timing_metrics(), FlowTiming, Flow timing analysis for hydrological characterization.  This module provides to, Calculate seasonal flow statistics.          Returns:             Dictionary wit, Calculate timing of flow extremes.          Returns:             Dictionary with, Analysis of temporal flow characteristics and seasonal patterns.      This class, Calculate flow duration and frequency metrics.          Returns:             Dic (+11 more)

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (26): range, _doy_climatology_fill(), _extract_raw_era5_batch(), fill_domain_edge(), fill_year_2023_partial(), _find_nearest_land_cells(), _load_centroids(), main() (+18 more)

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (18): calculate_extreme_metrics(), calculate_extreme_ratios(), FlowExtremes, Calculate drought-related flow indices.          Returns:             Dictionary, Analysis of flow extremes including high and low flow events.      This class pr, Calculate flood-related flow indices.          Returns:             Dictionary o, Calculate durations of consecutive events.          Args:             condition_, Initialize flow extremes analysis.          Args:             discharge: Dischar (+10 more)

### Community 28 - "Community 28"
Cohesion: 0.19
Nodes (25): calculate_event_response(), calculate_flashiness_index(), calculate_pq_cross_correlation(), calculate_temperature_aware_response_metrics(), calculate_temperature_partitioned_input(), detect_dead_years(), detect_precipitation_events(), detect_temperature_aware_dead_years() (+17 more)

### Community 29 - "Community 29"
Cohesion: 0.14
Nodes (21): Enum, count_flags_by_severity(), get_flag_severity(), has_critical_flag(), QualityFlag, Quality flag definitions for discharge assessment.  This module defines quality, Count flags by their severity level.      Args:         flags: List of quality f, Check if any flag has critical severity.      Args:         flags: List of quali (+13 more)

### Community 30 - "Community 30"
Cohesion: 0.14
Nodes (23): Flow Duration Curve analysis for hydrological characterization.  This module pro, Flow extremes analysis for hydrological characterization.  This module provides, Comprehensive hydrological indices for flow characterization.  This module provi, Flow variability analysis for hydrological characterization.  This module provid, Hydrological analysis package for CAMELS-RU dataset.  This package provides comp, aggregate_period_metrics(), calculate_comprehensive_metrics(), calculate_period_metrics() (+15 more)

### Community 31 - "Community 31"
Cohesion: 0.17
Nodes (22): _add_histogram_inset(), _create_bins_from_intervals(), _determine_bins(), _format_colorbar(), _get_aea_crs(), _plot_metric_points(), Plotting functions for continuous (float) metrics on Russia maps.  Reworked to m, Determine bin edges for metric.      Args:         metric: Metric column name. (+14 more)

### Community 32 - "Community 32"
Cohesion: 0.19
Nodes (21): build_daily_climatology(), calculate_peak_ratio(), calculate_year_deviation(), detect_climatology_anomalies(), detect_flat_years(), detect_seasonal_signal(), get_year_climatology_metrics(), Climatological pattern analysis for discharge quality assessment.  This module c (+13 more)

### Community 33 - "Community 33"
Cohesion: 0.14
Nodes (21): _add_histogram(), _get_aea_crs(), _plot_basemap(), _plot_points(), _plot_polygons(), _plot_ugms(), Return Albers Equal Area CRS for Russia., Plot polygons with metric column. (+13 more)

### Community 34 - "Community 34"
Cohesion: 0.16
Nodes (20): FlagSeverity, Severity levels for quality flags., assess_gauge_quality(), GaugeQualitySummary, get_gauge_summary(), Convert to dictionary for DataFrame creation., Perform comprehensive quality assessment for a gauge.      Args:         dischar, Quality assessment result for a single year. (+12 more)

### Community 35 - "Community 35"
Cohesion: 0.15
Nodes (17): Any, bool, int, Logger, LoggerAdapter, LogRecord, Path, str (+9 more)

### Community 36 - "Community 36"
Cohesion: 0.16
Nodes (20): get_optimal_workers(), _init_worker(), main(), merge_stream_saved_roi(), process_roi_watersheds(), process_single_watershed(), bool, float (+12 more)

### Community 37 - "Community 37"
Cohesion: 0.22
Nodes (20): compare_annual_variance(), detect_anomalies_all_years(), detect_constant_periods(), detect_data_quality_issues(), detect_implausible_spikes(), get_year_anomaly_metrics(), Statistical anomaly detection for discharge quality assessment.  This module det, Compare variance of a single year against long-term variance using F-test. (+12 more)

### Community 38 - "Community 38"
Cohesion: 0.18
Nodes (19): Any, float, GeoDataFrame, int, Logger, Path, str, _ensure_latlon() (+11 more)

### Community 39 - "Community 39"
Cohesion: 0.09
Nodes (28): _annual_ratios(), _budyko_curve(), _gauge_record(), main(), _plot(), DataFrame, DatetimeIndex, float (+20 more)

### Community 40 - "Community 40"
Cohesion: 0.18
Nodes (17): detect_covered_months(), _file_month(), filter_files_by_date(), filter_netcdf_candidates(), main(), process_single_watershed(), bool, float (+9 more)

### Community 41 - "Community 41"
Cohesion: 0.15
Nodes (17): BaseGeometry, area_from_gdf(), create_gdf(), min_max_xy(), poly_from_multipoly(), polygon_area(), Return biggest polygon if input is MultiPolygon; else return input.      Paramet, Create a GeoDataFrame (EPSG:4326) containing provided shape (largest polygon if (+9 more)

### Community 42 - "Community 42"
Cohesion: 0.20
Nodes (16): format_tile(), get_river_points(), Geometric helper functions.  All areas returned in square kilometers (km^2) unle, Round up to nearest multiple of round_val., Round down to nearest multiple of round_val., Find river tile file containing point (approx, based on naming scheme).      Par, Convert a space (or comma) separated string of numbers to numpy array.      Fall, Format tile name based on latitude and longitude.      Args:         lat: Latitu (+8 more)

### Community 43 - "Community 43"
Cohesion: 0.28
Nodes (16): compare_grade(), grade_tier(), load_precipitation(), load_temperature(), main(), markdown_table_from_frame(), markdown_table_from_series(), DataFrame (+8 more)

### Community 44 - "Community 44"
Cohesion: 0.18
Nodes (16): compare_discharge(), GRDCStation, load_grdc_stations(), main(), match_grdc_to_camels(), parse_grdc_file(), float, GeoDataFrame (+8 more)

### Community 45 - "Community 45"
Cohesion: 0.19
Nodes (15): grade_compound(), load_precipitation(), load_temperature(), bool, DataFrame, int, Path, Series (+7 more)

### Community 46 - "Community 46"
Cohesion: 0.25
Nodes (13): calculate_metrics_batched(), calculate_metrics_parallel(), _calculate_metrics_worker(), Parallel computation of hydrological metrics for multiple gauges.  This module p, Calculate metrics in batches for better memory management.      Useful when proc, Worker function for parallel metric calculation.      Args:         gauge_id: Un, Calculate comprehensive metrics for multiple gauges in parallel.      Uses multi, bool (+5 more)

### Community 47 - "Community 47"
Cohesion: 0.25
Nodes (13): create_forcing_netcdf(), get_gauge_list(), load_gauge_data(), main(), process_single_gauge(), ndarray, Path, str (+5 more)

### Community 48 - "Community 48"
Cohesion: 0.15
Nodes (12): Acknowledgments, CAMELS-RU: A Large-Sample Hydroclimatic Dataset for 3,353 Russian Catchments, Citation, Contact, Data Access, Data Processing Pipeline, Dataset Summary, Installation (+4 more)

### Community 49 - "Community 49"
Cohesion: 0.19
Nodes (13): find_float_len(), get_square_vertices(), inside_mask(), point_distance(), Return 2x2 rotation matrix for angle alpha (radians)., Return vertices (4x2) of a rotated square.      Parameters     ----------     ce, Great-circle distance (Haversine) between two points given in radians.      Retu, Check if point (x,y) strictly inside bounding box (x1,y1,x2,y2). (+5 more)

### Community 50 - "Community 50"
Cohesion: 0.23
Nodes (19): _build_forcing_tables(), _build_netcdf_schema(), _build_qc_summary(), _build_release_integrity(), main(), _preflight(), DataFrame, Path (+11 more)

### Community 51 - "Community 51"
Cohesion: 0.21
Nodes (11): _annual_mean_mm_yr(), _gauge_one(), main(), DatetimeIndex, float, ndarray, Series, str (+3 more)

### Community 52 - "Community 52"
Cohesion: 0.32
Nodes (12): bytes, download_target(), ensure_paper_bib_url(), ensure_paper_pdf_url(), fetch(), main(), Any, bool (+4 more)

### Community 53 - "Community 53"
Cohesion: 0.18
Nodes (10): CAMELS-RU — Agent Reference, Data root subdirectories (under `data/`), `data/` symlink can break silently when the external drive is unplugged, I. ENVIRONMENT, II. PATHS, III. KEY NUMBERS, IV. FORCING SOURCES, Per-file lint relaxations (from `pyproject.toml`) (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.33
Nodes (10): DataFrame, Figure, float, int, ndarray, _ensure_2d_array(), get_silhouette_scores(), plot_silhouette_range() (+2 more)

### Community 55 - "Community 55"
Cohesion: 0.20
Nodes (9): build_compound(), load_heights(), DataFrame, float, Series, str, Merge discharge and level data into compound per-gauge CSV files.  For each gaug, Load gauge zero elevations (m BS) from regular and GTS sources. (+1 more)

### Community 56 - "Community 56"
Cohesion: 0.28
Nodes (9): gauge_buffer_creator(), gauge_to_utm(), Create a square buffer for flood modelling extent around a gauge point.      Arg, Project a gauge geometry from WGS84 to its appropriate UTM zone.      Args:, For a point and a tile geopackage, find nearest river geometry.      Parameters, update_geometry(), Point, GeoDataFrame (+1 more)

### Community 57 - "Community 57"
Cohesion: 0.22
Nodes (8): Building LaTeX (for final submission), Building the canonical manuscript, CAMELS-RU Paper, Editing, Figures, Key Numbers, Review History, Structure

### Community 58 - "Community 58"
Cohesion: 0.38
Nodes (6): extract_year_grades(), main(), DataFrame, Path, Main execution function., Extract per-year grades from graded compound CSVs.      Reads CSVs from by_grade

### Community 59 - "Community 59"
Cohesion: 0.19
Nodes (12): kv(), main(), bool, str, Verify paper macros against the released CAMELS-RU v1.0 dataset.  Produces a dri, Print a report section heading., Print a labelled paper-versus-data comparison row., Print a report section heading. (+4 more)

### Community 60 - "Community 60"
Cohesion: 0.50
Nodes (3): main(), Regenerate only the map figures used in the CAMELS-RU manuscript.  Runs the thre, Run each notebook sequentially.

### Community 74 - "Community 74"
Cohesion: 0.15
Nodes (20): DataFrame, Index, object, Series, str, _as_string_index(), filter_paper_analysis_column(), filter_paper_analysis_index() (+12 more)

### Community 75 - "Community 75"
Cohesion: 0.18
Nodes (14): annual_cv_precip(), annual_mean_precip(), load_csv_series(), float, Path, Series, str, CAMELS-RU meteorological forcing diagnostics for the HESS manuscript.  Produces (+6 more)

### Community 76 - "Community 76"
Cohesion: 0.31
Nodes (13): calculate_annual_totals(), calculate_runoff_coefficient(), calculate_volume_relationship(), calculate_water_balance_metrics(), Water balance and precipitation-discharge relationship analysis.  This module pr, Calculate volume-based relationships between precipitation and discharge.      A, Calculate comprehensive water balance metrics.      Args:         precipitation_, Calculate annual total values from daily time series.      Args:         series: (+5 more)

### Community 77 - "Community 77"
Cohesion: 0.18
Nodes (12): find_extent(), Determine extent [min_lon, max_lon, min_lat, max_lat] snapped to grid resolution, Round x to nearest multiple of a while preserving reasonable decimal precision., round_nearest(), aggregation_definer(), nc_by_extent(), Select net_cdf by extent of given shape. Return masked net_cdf.      Args:, Determine aggregation method (sum or mean) for a variable based on dataset and v (+4 more)

### Community 78 - "Community 78"
Cohesion: 0.33
Nodes (5): cells, metadata, marimo_version, script_metadata_hash, version

### Community 80 - "Community 80"
Cohesion: 0.17
Nodes (11): _cluster_sort_key(), convert_q_cms_to_mm_day(), float, int, Series, str, CAMELS-RU hydrological signatures for the HESS manuscript.  Produces publication, Extract numeric cluster ID from 'Cluster N' string for sorting. (+3 more)

### Community 81 - "Community 81"
Cohesion: 0.14
Nodes (14): _find_gauge_id_column(), _gauge_ids_from_csv(), _normalize_id_header(), Index, Normalize a candidate gauge-ID field name for case/spacing variants., Return the gauge identifier column, accepting capitalization variants only., Normalize a candidate gauge-ID field name for case/spacing variants., Normalize a candidate gauge-ID field name for case/spacing variants. (+6 more)

### Community 82 - "Community 82"
Cohesion: 0.40
Nodes (4): grade_boxplot(), CAMELS-RU data description figures for the HESS manuscript.  Produces publicatio, Boxplot of *column* grouped by grade, with optional hydropower overlay.      Whe, Boxplot of *column* grouped by grade, with optional hydropower overlay.      Whe

### Community 83 - "Community 83"
Cohesion: 0.24
Nodes (13): _annual_mean_mm_yr(), _annual_ratios(), _build_budyko_aet(), _hydroclimate_worker(), _pct(), float, int, ndarray (+5 more)

### Community 84 - "Community 84"
Cohesion: 0.21
Nodes (12): _build_dam_excluded_analytics(), _build_subset_flow(), _load_release(), _parse_macro_int(), Any, str, Build HESS-facing summaries that exclude dam-regulated gauges by default.      C, Build HESS-facing summaries that exclude dam-regulated gauges by default.      C (+4 more)

### Community 85 - "Community 85"
Cohesion: 0.17
Nodes (12): _build_paper_analysis_scope(), _gauge_ids_from_frame(), GeoDataFrame, Extract gauge IDs from a tabular source without assuming lower-case headers., Extract gauge IDs from a tabular source without assuming lower-case headers., Extract gauge IDs from a tabular source without assuming lower-case headers., Extract gauge IDs from a tabular source without assuming lower-case headers., Write the gauge-ID-only exclusion used by manuscript analyses. (+4 more)

### Community 86 - "Community 86"
Cohesion: 0.17
Nodes (12): _build_strict_subset_trace(), _convert_q_cms_to_mm_day(), Convert discharge from cubic metres per second to mm per day., Reproduce strict map-subset gauge IDs from local intermediate data when present., Convert discharge from cubic metres per second to mm per day., Reproduce strict map-subset gauge IDs from local intermediate data when present., Convert discharge from cubic metres per second to mm per day., Reproduce strict map-subset gauge IDs from local intermediate data when present. (+4 more)

### Community 87 - "Community 87"
Cohesion: 0.22
Nodes (10): _build_gauge_id_length_audit(), _gauge_ids_from_netcdf(), Write gauge-ID length diagnostics while preserving the regulation proxy., Read gauge IDs from a NetCDF coordinate, accepting gauge_id/Gauge ID/gauge., Read gauge IDs from a NetCDF coordinate, accepting gauge_id/Gauge ID/gauge., Write gauge-ID length diagnostics only; no auxiliary attribute columns., Read gauge IDs from a NetCDF coordinate, accepting gauge_id/Gauge ID/gauge., Read gauge IDs from a NetCDF coordinate, accepting gauge_id/Gauge ID/gauge. (+2 more)

### Community 88 - "Community 88"
Cohesion: 0.50
Nodes (4): PreflightRow, One preflight check result., One preflight check result., One preflight check result.

## Knowledge Gaps
- **191 isolated node(s):** `Request`, `HTMLResponse`, `RedirectResponse`, `DataFrame`, `Logger` (+186 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `split_by_period()` connect `Community 30` to `Community 6`, `Community 39`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `paper_analysis_scope_summary()` connect `Community 74` to `Community 39`, `Community 75`, `Community 80`, `Community 82`, `Community 50`, `Community 85`, `Community 22`, `Community 59`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `calculate_comprehensive_metrics()` connect `Community 30` to `Community 4`, `Community 46`, `Community 6`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `QualityFlag` (e.g. with `GaugeQualitySummary` and `QualityGrade`) actually correct?**
  _`QualityFlag` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `assess_gauge_quality()` (e.g. with `run_temperature_aware_qc()` and `grade_compound()`) actually correct?**
  _`assess_gauge_quality()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `FlowVariability` (e.g. with `DatetimeIndex` and `float`) actually correct?**
  _`FlowVariability` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Request`, `HTMLResponse`, `RedirectResponse` to the rest of the system?**
  _806 weakly-connected nodes found - possible documentation gaps or missing edges._