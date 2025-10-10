# Visualization Improvement Guide: Handling Skewed Distributions

## Problem Statement

When visualizing hydrological metrics spatially, several metrics exhibited highly skewed distributions with extreme outliers:

- **mean_discharge**: Few very high values compressed 90% of data into narrow color range
- **Q5, Q95**: Flow extremes naturally have wide ranges
- **high_flow_duration, low_flow_duration**: Long-tailed distributions
- **runoff_ratio**: Occasional extreme values (>3.0)

**Result**: Maps became non-informative - most gauges appeared the same color, hiding spatial patterns.

## Solution Overview

Three-step approach to improve visualization without affecting analysis:

1. **Outlier Detection**: Identify extreme values using statistical methods
2. **Selective Filtering**: Remove only extreme outliers for visualization
3. **Improved Binning**: Use percentile-based color ranges

## Implementation

### Step 1: Outlier Detection

```python
def analyze_distribution(data):
    """Analyze distribution and identify outliers."""
    p1 = np.nanpercentile(data, 1)
    p25 = np.nanpercentile(data, 25)
    p75 = np.nanpercentile(data, 75)
    p99 = np.nanpercentile(data, 99)
    
    iqr = p75 - p25
    
    # Tukey's fence for extreme outliers
    lower_bound = p25 - 3 * iqr
    upper_bound = p75 + 3 * iqr
    
    # Skewness indicator
    skewness_ratio = (p99 - p1) / iqr
    
    return {
        'lower_bound': lower_bound,
        'upper_bound': upper_bound,
        'skewness_ratio': skewness_ratio
    }
```

**Interpretation:**
- **IQR method**: Standard approach (1.5×IQR = mild, 3×IQR = extreme)
- **Skewness ratio > 15**: Highly skewed, needs special treatment
- **Outlier %**: If >5%, filtering recommended

### Step 2: Filtering Strategy

Two methods depending on distribution:

#### Method A: IQR-based (moderately skewed)

```python
# For metrics like runoff_ratio, fdc_slope
q25 = np.nanpercentile(data, 25)
q75 = np.nanpercentile(data, 75)
iqr = q75 - q25

lower = q25 - 3 * iqr  # 3x for extreme outliers only
upper = q75 + 3 * iqr

filtered = data[(data >= lower) & (data <= upper)]
```

**When to use:** Skewness ratio 5-15

#### Method B: Percentile-based (highly skewed)

```python
# For metrics like mean_discharge, Q5, Q95, flow durations
lower = np.nanpercentile(data, 2)  # or 1
upper = np.nanpercentile(data, 98)  # or 99

filtered = data[(data >= lower) & (data <= upper)]
```

**When to use:** Skewness ratio > 15

### Step 3: Improved Binning

Use percentile-based value ranges:

```python
# Instead of using min/max for color range
vmin = data.min()  # BAD - sensitive to outliers
vmax = data.max()  # BAD - sensitive to outliers

# Use percentiles
vmin = np.nanpercentile(data, 2)  # GOOD - robust
vmax = np.nanpercentile(data, 98)  # GOOD - robust

# Pass to plotting function
russia_continuous_multiplot(
    ...,
    vmin_dict={'mean_discharge': vmin},
    vmax_dict={'mean_discharge': vmax},
    n_bins=8  # Increased from 6
)
```

## Metrics-Specific Settings

| Metric | Method | Percentiles/Multiplier | Typical % Removed |
|--------|--------|----------------------|-------------------|
| mean_discharge | Percentile | P2-P98 | 4% |
| runoff_ratio | IQR | 3×IQR | 2-3% |
| fdc_slope | IQR | 3×IQR | 2-3% |
| high_flow_avg_duration | Percentile | P1-P99 | 2% |
| low_flow_avg_duration | Percentile | P1-P99 | 2% |
| Q5 | Percentile | P2-P98 | 4% |
| Q95 | Percentile | P2-P98 | 4% |

## Results

### Before Filtering

```
Mean discharge:
  Range: 0.12 - 45.8 mm/day
  90% of data: 0.8 - 2.5 mm/day (compressed to 2-3 colors)
  10% of data: 2.5 - 45.8 mm/day (spread across 3-4 colors)
  → Spatial patterns invisible for majority of gauges
```

### After Filtering

```
Mean discharge (filtered):
  Range: 0.15 - 3.8 mm/day
  All data: 0.15 - 3.8 mm/day (spread across 8 colors)
  → Clear spatial gradients visible
  → Regional patterns interpretable
```

## Important Principles

### 1. Filtering Only for Visualization

```python
# Analysis uses FULL dataset
gauge_analysis = ...  # ALL gauges

# Visualization uses FILTERED dataset
gauge_analysis_viz = filter_outliers(gauge_analysis)  # Outliers removed

# Statistical analysis
metrics_df.describe()  # Uses ALL data
gauge_analysis.groupby(...).mean()  # Uses ALL data

# Plotting
plot_map(gauge_analysis_viz)  # Uses FILTERED data
```

### 2. Transparency

Always document:
- Number of gauges before/after filtering
- Filtering criteria used
- That filtering is visualization-only

```python
print(f"Plotting {len(gauge_analysis_viz)} gauges")
print(f"Original: {len(gauge_analysis)} gauges")
print(f"Removed: {len(gauge_analysis) - len(gauge_analysis_viz)} extreme outliers")
```

### 3. Validation

Check that filtering improves interpretability:

```python
# Before: Check color distribution
bins_before = pd.cut(gauge_analysis[metric], bins=6).value_counts()
# Should show imbalance (e.g., 90% in one bin)

# After: Check color distribution
bins_after = pd.cut(gauge_analysis_viz[metric], bins=8).value_counts()
# Should show better balance (e.g., 10-15% per bin)
```

## Best Practices

### 1. Choose Appropriate Thresholds

```python
# Conservative (remove <1%)
percentile_range = (0.5, 99.5)
iqr_multiplier = 4.0

# Standard (remove 2-4%)
percentile_range = (2, 98)  # RECOMMENDED
iqr_multiplier = 3.0  # RECOMMENDED

# Aggressive (remove 5-10%)
percentile_range = (5, 95)
iqr_multiplier = 2.0
```

**Recommendation**: Use standard thresholds (P2-P98 or 3×IQR)

### 2. Examine Distributions First

Always run distribution analysis before filtering:

```python
for metric in metrics:
    data = gdf[metric].dropna()
    
    # Print percentiles
    print(f"{metric}:")
    print(f"  P1-P99: {np.nanpercentile(data, [1, 99])}")
    print(f"  P25-P75: {np.nanpercentile(data, [25, 75])}")
    
    # Histogram
    plt.hist(data, bins=50)
    plt.title(metric)
    plt.show()
```

### 3. Create Comparison Plots

Show before/after to justify filtering:

```python
# Plot same metric before and after
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Before
plot_on_map(gauge_analysis, metric, ax=ax1, title="Before")

# After  
plot_on_map(gauge_analysis_viz, metric, ax=ax2, title="After")
```

## When NOT to Filter

Don't filter if:

1. **Few outliers** (<2% of data outside 3×IQR)
2. **Outliers are meaningful** (e.g., glacial catchments with extreme discharge)
3. **Analysis focus** is on extremes themselves
4. **Small sample** (n < 50 gauges)

Alternative: Use **log scale** colorbars for highly skewed data

## Implementation Checklist

- [ ] Analyze distribution (percentiles, IQR, skewness)
- [ ] Choose filtering method (IQR vs percentile)
- [ ] Set thresholds (conservative/standard/aggressive)
- [ ] Filter data → create `*_viz` dataset
- [ ] Set percentile-based vmin/vmax
- [ ] Increase bins (6→8 or 8→10)
- [ ] Create before/after comparison
- [ ] Document filtering in figure caption
- [ ] Verify analysis uses unfiltered data
- [ ] Check improved color distribution

## References

1. **Tukey's fence**: Tukey, J.W. (1977). Exploratory Data Analysis. Addison-Wesley.
2. **Robust statistics**: Huber, P.J. (2004). Robust Statistics. Wiley.
3. **Visualization best practices**: Tufte, E.R. (2001). The Visual Display of Quantitative Information.

---

**Summary**: Filtering extreme outliers (2-5% of data) for visualization improves spatial pattern interpretability without affecting statistical analysis. Use percentile-based methods for highly skewed metrics, IQR-based for moderately skewed metrics.
