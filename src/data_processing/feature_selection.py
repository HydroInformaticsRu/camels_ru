import pandas as pd


def select_uncorrelated_features(
    data: pd.DataFrame, threshold: float = 0.7, min_valid_fraction: float = 0.8
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
