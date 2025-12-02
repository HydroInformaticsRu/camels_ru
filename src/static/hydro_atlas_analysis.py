"""HydroATLAS cluster analysis utility functions.

Functions for catchment size categorization, feature filtering,
and cluster interpretation for CAMELS-RU dataset.
"""

import pandas as pd


def categorize_catchment_size(area: float) -> str:
    """Categorize catchment area into size classes.

    Args:
        area: Catchment area in km²

    Returns:
        Size category string with LaTeX formatting
    """
    lim_1, lim_2, lim_3, lim_4, lim_5 = 100, 2000, 10000, 50000, 200000

    if area < lim_1:
        return "a) < 100 $km^2$"
    elif (area >= lim_1) & (area <= lim_2):
        return "b) 100 $km^2$ - 2 000 $km^2$"
    elif (area > lim_2) & (area <= lim_3):
        return "c) 2 000 $km^2$ - 10 000 $km^2$"
    elif (area > lim_3) & (area <= lim_4):
        return "d) 10 000 $km^2$ - 50 000 $km^2$"
    elif (area > lim_4) & (area <= lim_5):
        return "e) 50 000 $km^2$ - 200 000 $km^2$"
    else:
        return "f) > 200 000 $km^2$"


def get_size_categories() -> list[str]:
    """Return ordered list of size category labels.

    Returns:
        List of size category strings
    """
    return [
        "a) < 100 $km^2$",
        "b) 100 $km^2$ - 2 000 $km^2$",
        "c) 2 000 $km^2$ - 10 000 $km^2$",
        "d) 10 000 $km^2$ - 50 000 $km^2$",
        "e) 50 000 $km^2$ - 200 000 $km^2$",
        "f) > 200 000 $km^2
    ]


def filter_hydroatlas_features(
    hydro_data: pd.DataFrame,
    gauge_index: pd.Index,
) -> tuple[pd.DataFrame, list[str]]:
    """Filter and select HydroATLAS features based on suffixes.

    Extracts features with specific HydroATLAS suffixes:
    - ult: ultimate (entire upstream watershed)
    - sse: sub-basin spatial extent
    - sav: sub-basin area-weighted average
    - use: upstream spatial extent
    - pva: point value attribute

    Args:
        hydro_data: DataFrame with HydroATLAS attributes
        gauge_index: Index of gauges to filter

    Returns:
        Tuple of (filtered_subset, selected_feature_names)
    """
    suffixes = ["yr", "lt", "av", "se", "pv"]
    prefix = ["u", "s"]

    filtered_tags = {}

    for tag in [
        i
        for i in hydro_data.columns
        if i.split("_")[-1] in [f"{p}{s}" for p in prefix for s in suffixes]
    ]:
        base_tag = "_".join(tag.split("_")[:2])
        if base_tag not in filtered_tags:
            filtered_tags[base_tag] = [tag]
        else:
            filtered_tags[base_tag].append(tag)

    selected_features = [v[0] if len(v) == 1 else v[1] for v in filtered_tags.values()]
    hydro_subset = hydro_data.loc[gauge_index, selected_features].copy()

    return hydro_subset, selected_features


def get_cluster_markers(n_clusters: int = 15) -> list[str]:
    """Return list of matplotlib marker symbols for cluster visualization.

    Args:
        n_clusters: Number of markers needed

    Returns:
        List of marker symbols
    """
    markers = ["o", "s", "^", "v", "<", ">", "D", "P", "X", "*", "h", "H", "8", "p", "d"]
    return markers[:n_clusters]


def get_cluster_colors(n_clusters: int = 15) -> list[str]:
    """Return list of color codes for cluster visualization.

    Args:
        n_clusters: Number of colors needed

    Returns:
        List of hex color codes
    """
    colors = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#aec7e8",
        "#ffbb78",
        "#98df8a",
        "#ff9896",
        "#c5b0d5",
    ]
    return colors[:n_clusters]


def get_marker_size_corrections() -> dict[str, float]:
    """Return marker size correction factors for visual balance.

    Different marker shapes require size adjustments to appear
    visually consistent.

    Returns:
        Dict mapping marker symbol to size correction factor
    """
    return {
        "o": 1.00,
        "^": 1.15,
        "v": 1.15,
        "<": 1.15,
        ">": 1.15,
        "d": 1.00,
        "p": 1.05,
        "h": 1.05,
        "H": 0.95,
        "8": 1.00,
        "X": 1.10,
        "*": 1.20,
        "D": 0.85,
        "P": 0.90,
        "s": 0.80,
    }


def classify_cluster_improved(
    cluster_id: int,
    cluster_centroids_detailed: pd.DataFrame,
    cluster_centroids_raw_detailed: pd.DataFrame,
    attribute_categories: dict[str, list[str]],
    threshold: float = 0.3,
) -> dict[str, str | dict | list]:
    """Classify cluster by dominant hydrological control.

    Uses standardized z-scores and category-based analysis to determine
    the dominant control type (Climate, Land Cover, Soil, etc.).

    Args:
        cluster_id: Cluster identifier (1-based)
        cluster_centroids_detailed: DataFrame with standardized centroids
        cluster_centroids_raw_detailed: DataFrame with raw centroids
        attribute_categories: Dict mapping category names to feature lists
        threshold: Z-score threshold for feature significance (default 0.3)

    Returns:
        Dict with keys: cluster_type, cluster_name, top_features, rationale
    """
    # Extract series for this cluster - type: ignore needed due to Pyright limitation
    centroid_std: pd.Series = cluster_centroids_detailed.loc[cluster_id]  # type: ignore
    centroid_raw: pd.Series = cluster_centroids_raw_detailed.loc[cluster_id]  # type: ignore

    # Find features with high absolute z-scores
    abs_values: pd.Series = centroid_std.abs()  # type: ignore
    mask = abs_values > threshold
    high_series: pd.Series = abs_values[mask].sort_values(ascending=False)  # type: ignore
    high_indices = high_series.index.tolist()

    # If we have clear dominant features
    if len(high_indices) > 0:
        top_feat = str(high_indices[0])
        z_val = float(centroid_std.loc[top_feat])
        raw_val = float(centroid_raw.loc[top_feat])

        # Determine category
        for category, features in attribute_categories.items():
            if top_feat in features:
                top_feats_dict = {f: float(centroid_std.loc[f]) for f in high_indices[:3]}
                return {
                    "cluster_type": category,
                    "cluster_name": f"{category} Controlled",
                    "top_features": top_feats_dict,
                    "rationale": f"Primary control: {top_feat} (z={z_val:.2f}, raw={raw_val:.2f})",
                }

    # Fallback: category-based scoring
    category_scores: dict[str, float] = {}
    for category, features in attribute_categories.items():
        cat_features = [f for f in features if f in centroid_std.index]
        if cat_features:
            abs_scores: pd.Series = centroid_std.loc[cat_features].abs()  # type: ignore
            category_scores[category] = float(abs_scores.mean())

    if category_scores:
        dominant_cat = max(category_scores.keys(), key=lambda k: category_scores[k])
        top_feats_dict = (
            {f: float(centroid_std.loc[f]) for f in high_indices[:3]} if high_indices else {}
        )
        return {
            "cluster_type": dominant_cat,
            "cluster_name": f"{dominant_cat} Influenced",
            "top_features": top_feats_dict,
            "rationale": f"Category mean z-score: {category_scores[dominant_cat]:.2f}",
        }

    # Ultimate fallback
    return {
        "cluster_type": "Mixed",
        "cluster_name": "Mixed Controls",
        "top_features": {},
        "rationale": "No clear dominant pattern",
    }


def get_attribute_categories() -> dict[str, list[str]]:
    """Return mapping of attribute categories to HydroATLAS features.

    Returns:
        Dict mapping category names to lists of feature codes
    """
    return {
        "Climate": ["pre_mm_syr", "pet_mm_syr", "aet_mm_syr", "snw_pc_syr", "glc_pc_use"],
        "Land Cover": [
            "for_pc_use",
            "crp_pc_use",
            "pst_pc_use",
            "ire_pc_use",
            "gla_pc_use",
            "prm_pc_use",
            "pac_pc_use",
            "tbi_cl_smj",
        ],
        "Soil": ["cly_pc_sav", "slt_pc_sav", "snd_pc_sav"],
        "Hydrogeology": ["kar_pc_use", "glh_cl_smj"],
        "Cryosphere": ["snw_pc_syr", "glc_pc_use"],
        "Water Bodies": ["lkv_mc_usu", "rev_mc_usu"],
        "Human Impact": ["dor_pc_pva", "urb_pc_use"],
    }
