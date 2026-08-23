from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import sys

import fiona
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))
from src.data_processing.gdal_processing import (
    create_tif_get_area,
    get_point_height_from_dem,
)
from src.data_processing.geom_functions import poly_from_multipoly
from src.utils.logger import setup_logger


def area_weighted_mean(data: np.ndarray, inter_areas: np.ndarray) -> np.ndarray:
    """Area-weighted mean of polygon attributes, normalised per variable over non-NaN polygons.

    Args:
        data: Attribute matrix of shape (n_polygons, n_variables); NaN marks no-data.
        inter_areas: Intersection area of each polygon with the catchment, shape (n_polygons,).

    Returns:
        Weighted mean per variable. Weights are normalised by the summed intersection area of
        the polygons that carry a value for that variable, so partial HydroATLAS coverage of the
        catchment does not scale the result. NaN where no polygon carries a value.
    """
    valid = ~np.isnan(data)
    weights = np.asarray(inter_areas, dtype="float64")[:, None] * valid
    weight_sum = weights.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (np.nan_to_num(data) * weights).sum(axis=0) / weight_sum
    return np.where(weight_sum > 0, out, np.nan)


logger = setup_logger(
    "hydroAtlasWS",
    log_file="logs/hydroAtlasWS.log",
)


class HydroAtlas:
    """Fast(er) HydroATLAS parser – stripped of per-row GeoPandas overhead."""

    monthes = tuple(f"{i:02d}" for i in range(1, 13))
    lc_classes = tuple(f"{i:02d}" for i in range(1, 23))
    pnv_classes = tuple(f"{i:02d}" for i in range(1, 16))  # Potential natural vegetation
    wetland_classes = tuple(f"{i:02d}" for i in range(1, 10))

    # ═══════════════════════════════════════════════════════════════════
    # HYDROLOGY - Discharge, runoff, inundation, lakes, rivers, groundwater
    # ═══════════════════════════════════════════════════════════════════
    hydrology_variables = [
        # Discharge (modeled)
        "dis_m3_pyr",  # Annual mean discharge
        "dis_m3_pmn",  # Annual minimum discharge
        "dis_m3_pmx",  # Annual maximum discharge
        # Runoff
        "run_mm_syr",  # Annual runoff
        # Inundation extent
        "inu_pc_smn",  # Sub-basin minimum inundation
        "inu_pc_umn",  # Upstream minimum inundation
        "inu_pc_smx",  # Sub-basin maximum inundation
        "inu_pc_umx",  # Upstream maximum inundation
        "inu_pc_slt",  # Sub-basin long-term max inundation
        "inu_pc_ult",  # Upstream long-term max inundation
        # Lake area and volume
        "lka_pc_sse",  # Lake area extent (sub-basin)
        "lka_pc_use",  # Lake area extent (upstream)
        "lkv_mc_usu",  # Lake volume (upstream at pour point)
        # Reservoir volume
        "rev_mc_usu",  # Reservoir volume (upstream)
        # Degree of regulation
        "dor_pc_pva",  # Degree of regulation index
        # River area and volume
        "ria_ha_ssu",  # River area (sub-basin)
        "ria_ha_usu",  # River area (upstream)
        "riv_tc_ssu",  # River volume (sub-basin)
        "riv_tc_usu",  # River volume (upstream)
        # Groundwater
        "gwt_cm_sav",  # Groundwater table depth
    ]

    # ═══════════════════════════════════════════════════════════════════
    # PHYSIOGRAPHY - Elevation, slope, stream gradient
    # ═══════════════════════════════════════════════════════════════════
    physiography_variables = [
        "ele_mt_sav",  # Elevation mean (sub-basin)
        "ele_mt_uav",  # Elevation mean (upstream)
        "ele_mt_smn",  # Elevation minimum (sub-basin)
        "ele_mt_smx",  # Elevation maximum (sub-basin)
        "slp_dg_sav",  # Terrain slope mean (sub-basin)
        "slp_dg_uav",  # Terrain slope mean (upstream)
        "sgr_dk_sav",  # Stream gradient mean
    ]

    # ═══════════════════════════════════════════════════════════════════
    # CLIMATE - Temperature, precipitation, PET, AET, aridity, snow
    # ═══════════════════════════════════════════════════════════════════
    climate_variables = [
        # Climate zones
        "clz_cl_smj",  # Climate zone (majority class)
        "cls_cl_smj",  # Climate strata (majority class)
        # Temperature - annual
        "tmp_dc_syr",  # Temperature annual mean (sub-basin)
        "tmp_dc_uyr",  # Temperature annual mean (upstream)
        "tmp_dc_smn",  # Temperature annual minimum (sub-basin)
        "tmp_dc_smx",  # Temperature annual maximum (sub-basin)
        # Temperature - monthly
        *tuple(f"tmp_dc_s{m}" for m in monthes),
        # Precipitation - annual
        "pre_mm_syr",  # Precipitation annual mean (sub-basin)
        "pre_mm_uyr",  # Precipitation annual mean (upstream)
        # Precipitation - monthly
        *tuple(f"pre_mm_s{m}" for m in monthes),
        # Potential evapotranspiration - annual
        "pet_mm_syr",  # PET annual mean (sub-basin)
        "pet_mm_uyr",  # PET annual mean (upstream)
        # Potential evapotranspiration - monthly
        *tuple(f"pet_mm_s{m}" for m in monthes),
        # Actual evapotranspiration - annual
        "aet_mm_syr",  # AET annual mean (sub-basin)
        "aet_mm_uyr",  # AET annual mean (upstream)
        # Actual evapotranspiration - monthly
        *tuple(f"aet_mm_s{m}" for m in monthes),
        # Aridity index
        "ari_ix_sav",  # Aridity index (sub-basin)
        "ari_ix_uav",  # Aridity index (upstream)
        # Climate moisture index - annual
        "cmi_ix_syr",  # CMI annual (sub-basin)
        "cmi_ix_uyr",  # CMI annual (upstream)
        # Climate moisture index - monthly
        *tuple(f"cmi_ix_s{m}" for m in monthes),
        # Snow cover - annual/max
        "snw_pc_syr",  # Snow cover annual mean (sub-basin)
        "snw_pc_uyr",  # Snow cover annual mean (upstream)
        "snw_pc_smx",  # Snow cover maximum (sub-basin)
        # Snow cover - monthly
        *tuple(f"snw_pc_s{m}" for m in monthes),
    ]

    # ═══════════════════════════════════════════════════════════════════
    # LAND COVER - GLC, PNV, wetlands, forest, crops, glaciers, etc.
    # ═══════════════════════════════════════════════════════════════════
    landcover_variables = [
        # Global Land Cover (GLC) - majority class
        "glc_cl_smj",
        # GLC - sub-basin percentages (22 classes)
        *tuple(f"glc_pc_s{c}" for c in lc_classes),
        # GLC - upstream percentages (22 classes)
        *tuple(f"glc_pc_u{c}" for c in lc_classes),
        # Potential Natural Vegetation (PNV) - majority class
        "pnv_cl_smj",
        # PNV - sub-basin percentages (15 classes)
        *tuple(f"pnv_pc_s{c}" for c in pnv_classes),
        # PNV - upstream percentages (15 classes)
        *tuple(f"pnv_pc_u{c}" for c in pnv_classes),
        # Wetlands - majority class
        "wet_cl_smj",
        # Wetland groups
        "wet_pc_sg1",  # Wetland group 1 (sub-basin)
        "wet_pc_ug1",  # Wetland group 1 (upstream)
        "wet_pc_sg2",  # Wetland group 2 (sub-basin)
        "wet_pc_ug2",  # Wetland group 2 (upstream)
        # Wetlands - individual classes (9 classes)
        *tuple(f"wet_pc_s{c}" for c in wetland_classes),
        *tuple(f"wet_pc_u{c}" for c in wetland_classes),
        # Specific land cover types
        "for_pc_sse",  # Forest extent (sub-basin)
        "for_pc_use",  # Forest extent (upstream)
        "crp_pc_sse",  # Cropland extent (sub-basin)
        "crp_pc_use",  # Cropland extent (upstream)
        "pst_pc_sse",  # Pasture extent (sub-basin)
        "pst_pc_use",  # Pasture extent (upstream)
        "ire_pc_sse",  # Irrigated area extent (sub-basin)
        "ire_pc_use",  # Irrigated area extent (upstream)
        "gla_pc_sse",  # Glacier extent (sub-basin)
        "gla_pc_use",  # Glacier extent (upstream)
        "prm_pc_sse",  # Permafrost extent (sub-basin)
        "prm_pc_use",  # Permafrost extent (upstream)
        "pac_pc_sse",  # Protected area extent (sub-basin)
        "pac_pc_use",  # Protected area extent (upstream)
        # Biomes and ecoregions (majority classes)
        "tbi_cl_smj",  # Terrestrial biome
        "tec_cl_smj",  # Terrestrial ecoregion
        "fmh_cl_smj",  # Freshwater major habitat type
        "fec_cl_smj",  # Freshwater ecoregion
    ]

    # ═══════════════════════════════════════════════════════════════════
    # SOILS & GEOLOGY - Texture, carbon, moisture, lithology, karst, erosion
    # ═══════════════════════════════════════════════════════════════════
    soil_and_geo_variables = [
        # Soil texture - sub-basin
        "cly_pc_sav",  # Clay fraction
        "slt_pc_sav",  # Silt fraction
        "snd_pc_sav",  # Sand fraction
        # Soil texture - upstream
        "cly_pc_uav",  # Clay fraction
        "slt_pc_uav",  # Silt fraction
        "snd_pc_uav",  # Sand fraction
        # Soil organic carbon
        "soc_th_sav",  # SOC (sub-basin)
        "soc_th_uav",  # SOC (upstream)
        # Soil water content - annual
        "swc_pc_syr",  # SWC annual (sub-basin)
        "swc_pc_uyr",  # SWC annual (upstream)
        # Soil water content - monthly
        *tuple(f"swc_pc_s{m}" for m in monthes),
        # Lithology (majority class)
        "lit_cl_smj",
        # Karst
        "kar_pc_sse",  # Karst extent (sub-basin)
        "kar_pc_use",  # Karst extent (upstream)
        # Erosion
        "ero_kh_sav",  # Soil erosion (sub-basin)
        "ero_kh_uav",  # Soil erosion (upstream)
    ]

    # ═══════════════════════════════════════════════════════════════════
    # ANTHROPOGENIC - Population, urban, lights, roads, footprint, GDP, HDI
    # ═══════════════════════════════════════════════════════════════════
    urban_variables = [
        # Population
        "pop_ct_ssu",  # Population count (sub-basin)
        "pop_ct_usu",  # Population count (upstream)
        "ppd_pk_sav",  # Population density (sub-basin)
        "ppd_pk_uav",  # Population density (upstream)
        # Urban extent
        "urb_pc_sse",  # Urban extent (sub-basin)
        "urb_pc_use",  # Urban extent (upstream)
        # Nighttime lights
        "nli_ix_sav",  # Nighttime lights (sub-basin)
        "nli_ix_uav",  # Nighttime lights (upstream)
        # Road density
        "rdd_mk_sav",  # Road density (sub-basin)
        "rdd_mk_uav",  # Road density (upstream)
        # Human footprint
        "hft_ix_s93",  # Human footprint 1993 (sub-basin)
        "hft_ix_u93",  # Human footprint 1993 (upstream)
        "hft_ix_s09",  # Human footprint 2009 (sub-basin)
        "hft_ix_u09",  # Human footprint 2009 (upstream)
        # Administrative
        "gad_id_smj",  # Administrative unit ID (majority)
        # GDP
        "gdp_ud_sav",  # GDP spatial average (sub-basin)
        "gdp_ud_ssu",  # GDP sum (sub-basin)
        "gdp_ud_usu",  # GDP sum (upstream)
        # Human Development Index
        "hdi_ix_sav",  # HDI (sub-basin)
    ]

    ALL_VARIABLES = (
        hydrology_variables
        + physiography_variables
        + climate_variables
        + landcover_variables
        + soil_and_geo_variables
        + urban_variables
    )

    # ═══════════════════════════════════════════════════════════════════
    # Unit scaling corrections (stored as integers with scaling factors)
    # ═══════════════════════════════════════════════════════════════════
    # Fields that need division by 10 to restore physical units
    _DIV10 = [
        # Lake area
        "lka_pc_sse",
        "lka_pc_use",
        # Degree of regulation
        "dor_pc_pva",
        # Terrain slope
        "slp_dg_sav",
        "slp_dg_uav",
        # Temperature (all monthly and annual)
        "tmp_dc_syr",
        "tmp_dc_uyr",
        "tmp_dc_smn",
        "tmp_dc_smx",
        *tuple(f"tmp_dc_s{m}" for m in monthes),
        # Human footprint indices
        "hft_ix_s93",
        "hft_ix_u93",
        "hft_ix_s09",
        "hft_ix_u09",
    ]

    # Fields that need division by 100 to restore physical units
    _DIV100 = [
        # Aridity index
        "ari_ix_sav",
        "ari_ix_uav",
        # Climate moisture index (all monthly and annual)
        "cmi_ix_syr",
        "cmi_ix_uyr",
        *tuple(f"cmi_ix_s{m}" for m in monthes),
    ]

    def __init__(self, tmp_flood_folder: str | Path = "/app/data/.tmp_flood") -> None:
        """Initialize HydroATLAS parser.

        Args:
            tmp_flood_folder: Directory for temporary flood/DEM processing files.
        """
        self.tmp_flood_folder = Path(tmp_flood_folder)

    # -----------------------------------------------------------------
    def feature_extractor(
        self,
        *,
        user_ws: Polygon,
        gdb_file_path: str | Path,
        user_gauge: gpd.GeoSeries,
        elevation_paths: str | Path,
        fdir_paths: str | Path,
        gauge_id: str,
    ) -> pd.Series:
        """Extract area-weighted HydroATLAS attributes for user watershed.

        Implements the Caravan methodology for HydroATLAS aggregation:
        weights = intersection_area / total_catchment_area (not native polygon area).

        Args:
            user_ws: User watershed polygon (may be MultiPolygon).
            gdb_file_path: Path to HydroATLAS GDB file.
            user_gauge: GeoSeries containing gauge point geometry.
            elevation_paths: Path to elevation/DEM storage directory.
            fdir_paths: Path to flow direction raster.
            gauge_id: Unique identifier for the gauge.

        Returns:
            Series of area-weighted HydroATLAS attributes plus derived fields.

        Raises:
            ValueError: If no HydroATLAS polygons overlap with user watershed.
        """
        # ── 1.  Pre-read & quick geometry prep ────────────────────────
        user_poly = poly_from_multipoly(user_ws)  # shapely Polygon
        layer = fiona.listlayers(gdb_file_path)[-1]

        gdf = gpd.read_file(
            gdb_file_path,
            layer=layer,
            mask=user_poly,
            ignore_geometry=False,
        )
        gdf.replace(-9999, np.nan, inplace=True)
        gdf["geometry"] = gdf["geometry"].map(poly_from_multipoly)

        # Project to equal-area CRS for accurate area calculations
        # Use appropriate UTM zone or equal-area projection based on centroid
        original_crs = gdf.crs
        if original_crs is None or original_crs.is_geographic:
            # Estimate UTM zone from watershed centroid
            centroid_lon = user_poly.centroid.x
            utm_zone = int((centroid_lon + 180) / 6) + 1
            hemisphere = "north" if user_poly.centroid.y >= 0 else "south"
            epsg_base = 32600 if hemisphere == "north" else 32700
            target_crs = f"EPSG:{epsg_base + utm_zone}"

            gdf_projected = gdf.to_crs(target_crs)
            user_poly_projected = gpd.GeoSeries([user_poly], crs=original_crs or "EPSG:4326").to_crs(
                target_crs
            )[0]
        else:
            gdf_projected = gdf
            user_poly_projected = user_poly

        # Calculate areas in projected CRS (meters)
        user_catchment_area = user_poly_projected.area
        geom_projected = gdf_projected["geometry"]
        inter_areas = np.asarray(
            [poly.intersection(user_poly_projected).area for poly in geom_projected]
        )

        # Filter small artifacts (<5 km²) per Caravan methodology
        min_area_threshold = 5_000_000  # 5 km² in m²
        valid_mask = inter_areas >= min_area_threshold
        inter_areas = inter_areas[valid_mask]
        gdf = gdf[valid_mask].copy()

        # bail early if watershed does not overlap HydroATLAS
        if len(inter_areas) == 0 or inter_areas.sum() == 0:
            raise ValueError(f"No HydroATLAS overlap for gauge <{gauge_id}>")

        # ── 2.  Area-weighted aggregation (Caravan methodology) ───────
        data = gdf[self.ALL_VARIABLES].to_numpy(dtype="float32", copy=False)
        geo_vector = pd.Series(area_weighted_mean(data, inter_areas), index=self.ALL_VARIABLES)

        # ── 3.  Unit corrections ──────────────────────────────────────
        geo_vector.loc[self._DIV10] /= 10.0
        geo_vector.loc[self._DIV100] /= 100.0

        # ── 4.  Add basin-specific extras (area, acc, z, lat/lon) ─────
        acc_coef, ws_area = create_tif_get_area(
            self.tmp_flood_folder,
            gauge_id,
            user_gauge,
            user_poly,
            fdir_path=Path(fdir_paths),
            result_tiff_storage=Path(elevation_paths),
        )
        geo_vector["ws_area"] = ws_area
        geo_vector["acc"] = acc_coef
        geo_vector["height_bs"] = get_point_height_from_dem(
            pt_geoser=user_gauge, dem_path=f"{elevation_paths}/{gauge_id}.tiff"
        )

        # Extract point coordinates with proper type checking
        from shapely.geometry import Point

        gauge_geom = user_gauge.geometry.values[0]
        if isinstance(gauge_geom, Point):
            geo_vector["lat"], geo_vector["lon"] = gauge_geom.y, gauge_geom.x
        else:
            # Fallback for non-Point geometries
            centroid = gauge_geom.centroid
            geo_vector["lat"], geo_vector["lon"] = centroid.y, centroid.x

        # Add metadata about aggregation quality
        geo_vector["area_fraction_used"] = inter_areas.sum() / user_catchment_area
        geo_vector["n_hydroatlas_polygons"] = len(inter_areas)

        return geo_vector

    # -----------------------------------------------------------------
    @staticmethod
    def save_results(extracted: Sequence[pd.Series], gauge_ids: Sequence[str], out_dir: Path) -> None:
        """Thread-safe disk-append of results."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = pd.concat(extracted, axis=1).T
        result.index = pd.Index(gauge_ids, name="gauge_id")

        csv_path = out_dir / "geo_vector.csv"
        if csv_path.exists():
            result = result.combine_first(pd.read_csv(csv_path, index_col="gauge_id"))
        result.to_csv(csv_path, float_format="%.6g")


# ── convenience wrapper; picklable for ProcessPool -------------------
def ha_worker(
    gauge_id: str,
    *,
    ws,
    gauge,
    gdb_path,
    elev_path,
    fdir_path,
    tmp_dir,
) -> tuple[str, pd.Series]:
    """Worker function for parallel HydroATLAS extraction.

    Args:
        gauge_id: Unique gauge identifier.
        ws: Watershed polygon geometry.
        gauge: GeoSeries with gauge point.
        gdb_path: Path to HydroATLAS GDB.
        elev_path: Elevation data directory.
        fdir_path: Flow direction raster path.
        tmp_dir: Temporary processing directory.

    Returns:
        Tuple of (gauge_id, extracted attributes Series).
    """
    parser = HydroAtlas(tmp_flood_folder=tmp_dir)
    series = parser.feature_extractor(
        user_ws=ws,
        gdb_file_path=gdb_path,
        user_gauge=gauge,
        elevation_paths=elev_path,
        fdir_paths=fdir_path,
        gauge_id=gauge_id,
    )
    return gauge_id, series


def load_static_data(data_path: str, valid_gauges: list[str]) -> pd.DataFrame:
    """Load and filter static data for valid gauges."""
    static_data = pd.read_csv(data_path, dtype={"gage_id": str}, index_col="gage_id")

    return static_data.loc[valid_gauges, :]


def select_uncorrelated_features(
    data: pd.DataFrame,
    threshold: float = 0.75,
    min_valid_fraction: float = 0.8,
) -> list[str]:
    """Select features from the DataFrame.

    Features are not highly correlated, have sufficient valid data,
    and do not contain '_cl_' in their names.

    Args:
        data: Input DataFrame with features.
        threshold: Absolute correlation threshold above which features are considered correlated.
        min_valid_fraction: Minimum fraction of non-zero and non-NaN values required to keep a feature.

    Returns:
        List of column names representing uncorrelated features with sufficient valid data
        and without '_cl_' in their names.
    """
    import numpy as np

    # Exclude columns containing '_cl_' in their names
    filtered_cols = [col for col in data.columns if "_cl_" not in col]
    filtered_data = data[filtered_cols]

    # Filter out columns with less than min_valid_fraction valid (non-zero, non-NaN) data
    valid_mask = (filtered_data != 0) & (~filtered_data.isna())
    valid_fraction = valid_mask.sum(axis=0) / len(filtered_data)
    sufficient_data_cols = valid_fraction[valid_fraction >= min_valid_fraction].index.tolist()

    # Subset data to columns with sufficient valid data
    filtered_data = filtered_data[sufficient_data_cols]

    # Compute the absolute correlation matrix
    corr_matrix = filtered_data.corr().abs()

    # Select upper triangle of correlation matrix
    upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))

    # Identify columns to drop based on correlation threshold
    to_drop = set()
    for col in upper.columns:
        if any(upper[col] > threshold):
            to_drop.add(col)

    # Features to keep are those not in to_drop
    selected_features = [col for col in filtered_data.columns if col not in to_drop]
    return selected_features


def get_combined_features(
    static_data: pd.DataFrame,
) -> tuple[list[str], pd.DataFrame]:
    """Select and combine static features."""
    old_static_features = [
        "for_pc_sse",
        "crp_pc_sse",
        "inu_pc_ult",
        "ire_pc_sse",
        "lka_pc_use",
        "prm_pc_sse",
        "pst_pc_sse",
        "cly_pc_sav",
        "slt_pc_sav",
        "snd_pc_sav",
        "kar_pc_sse",
        "urb_pc_sse",
        "gwt_cm_sav",
        "lkv_mc_usu",
        "rev_mc_usu",
        "sgr_dk_sav",
        "slp_dg_sav",
        "ws_area",
        "ele_mt_sav",
    ]
    uncorrelated_static_features = select_uncorrelated_features(static_data)
    combined_feature = sorted(set(old_static_features + uncorrelated_static_features))
    combined_features_df = static_data[combined_feature].reset_index()
    logger.info(f"Selected {len(combined_feature)} uncorrelated features from static_data.")
    return combined_feature, combined_features_df
