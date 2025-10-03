from __future__ import annotations

from collections.abc import Sequence
import itertools
from pathlib import Path
import sys

import fiona
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))
from src.data_processing.gdal_processing import create_tif_get_area, get_point_height_from_dem
from src.data_processing.geom_functions import poly_from_multipoly
from src.utils.logger import setup_logger

logger = setup_logger(
    "hydroAtlasWS",
    log_file="logs/hydroAtlasWS.log",
)


class HydroAtlas:
    """Fast(er) HydroATLAS parser – stripped of per-row GeoPandas overhead."""

    monthes = tuple(f"{i:02d}" for i in range(1, 13))
    lc_classes = tuple(f"{i:02d}" for i in range(1, 23))
    wetland_classes = tuple(f"{i:02d}" for i in range(1, 10))

    hydrology_variables = [
        "inu_pc_ult",
        "lka_pc_use",
        "lkv_mc_usu",
        "rev_mc_usu",
        "dor_pc_pva",
        "gwt_cm_sav",
    ]

    physiography_variables = ["ele_mt_sav", "slp_dg_sav", "sgr_dk_sav"]

    climate_variables = [
        "clz_cl_smj",
        "cls_cl_smj",
        *tuple(f"tmp_dc_s{m}" for m in monthes),
        *tuple(f"pre_mm_s{m}" for m in monthes),
        *tuple(f"pet_mm_s{m}" for m in monthes),
        *tuple(f"aet_mm_s{m}" for m in monthes),
        "ari_ix_sav",
        *tuple(f"cmi_ix_s{m}" for m in monthes),
        *tuple(f"snw_pc_s{m}" for m in monthes),
    ]

    landcover_variables = [
        "glc_cl_smj",
        *tuple(f"glc_pc_s{c}" for c in lc_classes),
        *tuple(f"wet_pc_s{c}" for c in wetland_classes),
        "for_pc_sse",
        "crp_pc_sse",
        "pst_pc_sse",
        "ire_pc_sse",
        "gla_pc_sse",
        "prm_pc_sse",
    ]

    soil_and_geo_variables = [
        "cly_pc_sav",
        "slt_pc_sav",
        "snd_pc_sav",
        "soc_th_sav",
        "swc_pc_syr",
        *tuple(f"swc_pc_s{m}" for m in monthes),
        "kar_pc_sse",
        "ero_kh_sav",
    ]

    urban_variables = ["urb_pc_sse", "hft_ix_s93", "hft_ix_s09"]

    ALL_VARIABLES = [
        hydrology_variables
        + physiography_variables
        + climate_variables
        + landcover_variables
        + soil_and_geo_variables
        + urban_variables
    ]

    ALL_VARIABLES = list(itertools.chain(*ALL_VARIABLES))

    # fields that need scaling back to physical units
    _DIV10 = [
        "lka_pc_use",
        "dor_pc_pva",
        "slp_dg_sav",
        *tuple(f"tmp_dc_s{m}" for m in monthes),
        "hft_ix_s93",
        "hft_ix_s09",
    ]
    _DIV100 = ["ari_ix_sav", *tuple(f"cmi_ix_s{m}" for m in monthes)]

    def __init__(self, tmp_flood_folder: str | Path = "/app/data/.tmp_flood") -> None:
        self.tmp_flood_folder = Path(tmp_flood_folder)

    # -----------------------------------------------------------------
    def featureXtractor(
        self,
        *,
        user_ws: Polygon,
        gdb_file_path: str | Path,
        user_gauge: gpd.GeoSeries,
        elevation_paths: str | Path,
        fdir_paths: str | Path,
        gauge_id: str,
    ) -> pd.Series:
        """Weighted mean of HydroATLAS vars clipped to `user_ws`."""
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
        gdf["geometry"] = gdf["geometry"].apply(poly_from_multipoly)

        geom = gdf["geometry"]
        native_areas = np.asarray([poly.area for poly in geom])
        inter_areas = np.asarray([poly.intersection(user_poly).area for poly in geom])
        with np.errstate(divide="ignore", invalid="ignore"):
            weights = np.where(native_areas > 0, inter_areas / native_areas, 0.0)

        # bail early if watershed does not overlap HydroATLAS
        if weights.sum() == 0:
            raise ValueError(f"No HydroATLAS overlap for gauge <{gauge_id}>")

        # ── 2.  Weighted aggregation (vectorised) ─────────────────────
        data = gdf[self.ALL_VARIABLES].to_numpy(dtype="float32", copy=False)
        num = np.nan_to_num(data) * weights[:, None]
        geo_vector = pd.Series(num.sum(axis=0) / weights.sum(), index=self.ALL_VARIABLES)

        # ── 3.  Unit corrections ──────────────────────────────────────
        geo_vector.loc[self._DIV10] /= 10.0
        geo_vector.loc[self._DIV100] /= 100.0

        # ── 4.  Add basin-specific extras (area, acc, z, lat/lon) ─────
        acc_coef, ws_area = create_tif_get_area(
            self.tmp_flood_folder,
            gauge_id,
            user_gauge,
            user_poly,
            fdir_path=fdir_paths,
            result_tiff_storage=elevation_paths,
        )
        geo_vector["ws_area"] = ws_area
        geo_vector["acc"] = acc_coef
        geo_vector["height_bs"] = get_point_height_from_dem(
            pt_geoser=user_gauge, dem_path=f"{elevation_paths}/{gauge_id}.tiff"
        )

        pt = user_gauge.geometry.values[0]
        geo_vector["lat"], geo_vector["lon"] = pt.y, pt.x
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
    parser = HydroAtlas(tmp_flood_folder=tmp_dir)
    series = parser.featureXtractor(
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
    data: pd.DataFrame, threshold: float = 0.75, min_valid_fraction: float = 0.8
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


def get_combined_features(static_data: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
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
