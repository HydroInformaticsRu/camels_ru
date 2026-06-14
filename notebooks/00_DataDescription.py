"""CAMELS-RU data description figures for the HESS manuscript.

Produces publication-quality figures for Sections 2, 5.1–5.3:
  - fig_gauge_network.png      (Sec 2: study area, gauge network, catchment sizes)
  - fig_hydro_characteristics.png  (Sec 5.1–5.2: discharge & level stats by grade)
  - fig_quality_assessment.png (Sec 5.3: quality grading, completeness, coverage)

Design choices:
  - Colorblind-safe Paul Tol palette (no green/red pairing)
  - Boxplots instead of overlapping histograms (class imbalance handled)
  - No pie charts (discouraged in geoscience journals)
  - No country borders or basemap (politically sensitive)
  - Gauge IDs with seven or more characters are retained in the release but
    excluded from the manuscript-analysis figures and paper-facing summaries
"""

from pathlib import Path
import sys
import warnings

import geopandas as gpd
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from src.static.hydro_atlas_analysis import (  # noqa: E402
    categorize_catchment_size,
    get_size_categories,
)
from src.utils.paper_analysis_scope import (  # noqa: E402
    PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH,
    PAPER_ANALYSIS_EXCLUSION_NOTE,
    filter_paper_analysis_index,
    is_paper_analysis_excluded_gauge_id,
    paper_analysis_scope_summary,
)

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

# ── Style ────────────────────────────────────────────────────────────────────
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
    }
)

# ── Colorblind-safe palette (Paul Tol bright) ───────────────────────────────
GRADE_COLORS = {
    "A": "#4477AA",  # blue
    "B": "#66CCEE",  # cyan
    "C": "#CCBB44",  # yellow
    "D": "#EE6677",  # pink
    "F": "#AA3377",  # purple
    "ungraded": "#BBBBBB",  # grey
}
GRADE_ORDER = ["A", "B", "C", "D", "F", "ungraded"]
HYDRO_ID_MIN_LEN = PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
COMPOUND_DIR = DATA_DIR / "HydroData" / "Compound"
GEOM_DIR = DATA_DIR / "geometry"
IMAGE_DIR = PROJECT_ROOT / "paper" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)


# ── Helper ───────────────────────────────────────────────────────────────────
def grade_boxplot(
    ax,
    data_df,
    column,
    ylabel,
    title,
    *,
    log_scale=False,
    show_hydropower=False,
):
    """Boxplot of *column* grouped by grade, with optional hydropower overlay.

    When *show_hydropower* is True, hydropower stations are excluded from the
    box-and-whisker distribution (preventing y-axis compression) and overlaid
    as black triangles.
    """
    has_hp_col = "is_hydropower" in data_df.columns
    plot_data = []
    plot_labels = []
    plot_colors = []

    for grade in GRADE_ORDER:
        mask = data_df["grade"] == grade
        if show_hydropower and has_hp_col:
            mask = mask & ~data_df["is_hydropower"]
        vals = data_df[mask][column].dropna()
        if len(vals) == 0:
            continue
        if log_scale:
            vals = np.log10(vals.clip(lower=0.01))
        plot_data.append(vals.values)
        plot_labels.append(grade)
        plot_colors.append(GRADE_COLORS[grade])

    bp = ax.boxplot(
        plot_data,
        tick_labels=plot_labels,
        patch_artist=True,
        widths=0.6,
        flierprops={"markersize": 2, "alpha": 0.3},
        medianprops={"color": "black", "linewidth": 1.5},
    )
    for patch, color in zip(bp["boxes"], plot_colors, strict=False):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Overlay hydropower stations as black triangles
    if show_hydropower and "is_hydropower" in data_df.columns:
        first_hp = True
        for i, grade in enumerate(plot_labels):
            hp_vals = data_df[(data_df["grade"] == grade) & data_df["is_hydropower"]][column].dropna()
            if len(hp_vals) == 0:
                continue
            v = np.log10(hp_vals.clip(lower=0.01)) if log_scale else hp_vals
            ax.scatter(
                [i + 1] * len(v),
                v,
                marker="^",
                c="black",
                s=18,
                zorder=5,
                alpha=0.8,
                label=f"Hydropower (n={data_df['is_hydropower'].sum()})" if first_hp else None,
            )
            first_hp = False

    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.grid(alpha=0.2, axis="y", linestyle="--")


# ══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════

ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
ws.set_index("gauge_id", inplace=True)
ws.index = ws.index.astype(str)

gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
gauge.set_index("gauge_id", inplace=True)
gauge.index = gauge.index.astype(str)

release_scope = paper_analysis_scope_summary(ws.index)
ws = filter_paper_analysis_index(ws)
gauge = filter_paper_analysis_index(gauge)

quality_df = pd.read_csv(COMPOUND_DIR / "quality_summary.csv")
quality_df["gauge_id"] = quality_df["gauge_id"].astype(str)
quality_df.set_index("gauge_id", inplace=True)

# Merge grade + hydropower flag into gauge points
gauge["grade"] = gauge.index.map(
    lambda gid: (
        quality_df.loc[gid, "overall_grade"]
        if gid in quality_df.index and pd.notna(quality_df.loc[gid, "overall_grade"])
        else "ungraded"
    )
)
gauge["is_hydropower"] = gauge.index.str.len() >= HYDRO_ID_MIN_LEN

print(f"Total release watersheds: {release_scope.n_total}")
print(f"Paper-analysis watersheds: {len(ws)}")
print(f"Paper-analysis gauges:     {len(gauge)}")
print(
    f"Gauge-ID excluded from paper analyses (ID≥{HYDRO_ID_MIN_LEN} chars): "
    f"{release_scope.n_excluded}"
)
print(PAPER_ANALYSIS_EXCLUSION_NOTE)

print("\n=== Grade Distribution ===")
for grade, count in gauge["grade"].value_counts().reindex(GRADE_ORDER).items():
    print(f"  {grade}: {count} ({count / len(gauge) * 100:.1f}%)")

# ── Watershed size categories ────────────────────────────────────────────────
ws["size_category"] = ws["area_km2"].apply(categorize_catchment_size)
ws["size_category"] = pd.Categorical(ws["size_category"], categories=get_size_categories())
size_counts = ws["size_category"].value_counts(sort=False)

print("\n=== Watershed Size Distribution ===")
for cat, cnt in size_counts.items():
    print(f"  {cat}: {cnt} ({cnt / len(ws) * 100:.1f}%)")

# ── Scan compound files (single pass for Q and H) ───────────────────────────
print("\n=== Scanning Compound Files ===")
_META_FILES = {"quality_summary.csv", "grade_mapping.json"}
compound_files = sorted(f for f in COMPOUND_DIR.glob("*.csv") if f.name not in _META_FILES)

discharge_stats = []
level_stats = []

for csv_path in compound_files:
    gid = csv_path.stem
    if is_paper_analysis_excluded_gauge_id(gid):
        continue
    df = pd.read_csv(csv_path, index_col="date", parse_dates=True)
    grade = quality_df.loc[gid, "overall_grade"] if gid in quality_df.index else np.nan
    grade_label = grade if pd.notna(grade) else "ungraded"
    is_hp = len(gid) >= HYDRO_ID_MIN_LEN

    # Discharge
    if "q_cms" in df.columns and df["q_cms"].notna().any():
        q = df["q_cms"]
        q_valid = q.dropna()
        discharge_stats.append(
            {
                "gauge_id": gid,
                "grade": grade_label,
                "is_hydropower": is_hp,
                "n_years": (q_valid.index.max() - q_valid.index.min()).days / 365.25,
                "mean_q_cms": q_valid.mean(),
                "q_cv": q_valid.std() / q_valid.mean() if q_valid.mean() > 0 else np.nan,
                "missing_pct": q.isna().sum() / len(q) * 100,
            }
        )

    # Water levels
    if "lvl_sm" in df.columns and df["lvl_sm"].notna().any():
        lvl = df["lvl_sm"]
        lvl_valid = lvl.dropna()
        level_stats.append(
            {
                "gauge_id": gid,
                "grade": grade_label,
                "is_hydropower": is_hp,
                "n_years": (lvl_valid.index.max() - lvl_valid.index.min()).days / 365.25,
                "mean_lvl_sm": lvl_valid.mean(),
                "lvl_range": lvl_valid.max() - lvl_valid.min(),
                "has_negatives": (lvl_valid < 0).any(),
                "missing_pct": lvl.isna().sum() / len(lvl) * 100,
            }
        )

q_df = pd.DataFrame(discharge_stats).set_index("gauge_id")
lvl_df = pd.DataFrame(level_stats).set_index("gauge_id")

print(f"Gauges with discharge: {len(q_df)} (hydropower: {q_df['is_hydropower'].sum()})")
print(f"Gauges with levels:    {len(lvl_df)} (hydropower: {lvl_df['is_hydropower'].sum()})")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — Gauge network & catchment sizes  (Section 2)
# ══════════════════════════════════════════════════════════════════════════════

import cartopy.crs as ccrs  # noqa: E402, I001

from src.plots.paper_maps import get_russia_projection  # noqa: E402

_aea = get_russia_projection()
_data_crs = ccrs.PlateCarree()

fig = plt.figure(figsize=(14.0, 5.5), constrained_layout=True)
gs = fig.add_gridspec(1, 2, width_ratios=[2.2, 1])
ax_map = fig.add_subplot(gs[0, 0], projection=_aea)
ax_hist = fig.add_subplot(gs[0, 1])

ax_map.axis("off")

# Set extent from gauge data
from src.plots.paper_maps import _set_extent_from_data  # noqa: E402

_set_extent_from_data(ax_map, gauge)

# Natural Earth coastline (no political borders)
_ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
_ne_land.to_crs(_aea.proj4_init).plot(
    ax=ax_map, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1
)

# (a) Gauge locations by grade — ungraded first (background), then graded on top
for grade in reversed(GRADE_ORDER):
    subset = gauge[gauge["grade"] == grade]
    if len(subset) == 0:
        continue
    regular = subset[~subset["is_hydropower"]]
    hydro = subset[subset["is_hydropower"]]
    zorder = 2 if grade == "ungraded" else 3

    if len(regular) > 0:
        ax_map.scatter(
            regular.geometry.x,
            regular.geometry.y,
            s=8,
            alpha=0.7,
            c=GRADE_COLORS[grade],
            label=f"{grade} (n={len(subset)})",
            edgecolors="none",
            zorder=zorder,
            transform=_data_crs,
        )
    if len(hydro) > 0:
        ax_map.scatter(
            hydro.geometry.x,
            hydro.geometry.y,
            s=20,
            alpha=0.8,
            c=GRADE_COLORS[grade],
            marker="^",
            edgecolors="black",
            linewidths=0.4,
            zorder=4,
            transform=_data_crs,
        )

ax_map.set_title("(a) Gauge network", fontsize=13, fontweight="bold", loc="left")
# Reverse legend so Grade A appears first; add hydropower marker only if any remain in scope
handles, labels = ax_map.get_legend_handles_labels()
all_handles = handles[::-1]
all_labels = labels[::-1]
n_hydro_in_scope = int(gauge["is_hydropower"].sum())
if n_hydro_in_scope:
    hp_handle = Line2D(
        [],
        [],
        marker="^",
        color="none",
        markerfacecolor="#888888",
        markeredgecolor="black",
        markersize=6,
        linestyle="None",
        label=f"Hydropower (n={n_hydro_in_scope})",
    )
    all_handles.append(hp_handle)
    all_labels.append(hp_handle.get_label())
ax_map.legend(
    all_handles,
    all_labels,
    loc="lower left",
    fontsize=8,
    framealpha=0.9,
    markerscale=2.0,
    ncol=2,
    columnspacing=0.8,
    handletextpad=0.4,
)

# (b) Catchment size distribution (horizontal bars for readability)
clean_labels = [cat.split(") ")[1].replace("$km^2$", "km²") for cat in size_counts.index]
bars = ax_hist.barh(
    range(len(size_counts)),
    size_counts.values,
    color="#4477AA",
    edgecolor="black",
    linewidth=0.5,
)
ax_hist.set_yticks(range(len(size_counts)))
ax_hist.set_yticklabels(clean_labels, fontsize=10)
ax_hist.set_xlabel("Number of catchments", fontsize=12)
ax_hist.set_title("(b) Size distribution", fontsize=13, fontweight="bold", loc="left")
ax_hist.grid(alpha=0.15, axis="x", linestyle="--")
ax_hist.invert_yaxis()

for bar, cnt in zip(bars, size_counts.values, strict=False):
    ax_hist.text(
        cnt + 20,
        bar.get_y() + bar.get_height() / 2,
        f"{cnt}",
        va="center",
        fontsize=10,
        fontweight="bold",
    )

fig.savefig(IMAGE_DIR / "fig_gauge_network.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("\nSaved: fig_gauge_network.png")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — Discharge & level characteristics  (Section 5.1–5.2)
# ══════════════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(2, 3, figsize=(14.0, 8.0), constrained_layout=True)

# Top row — Discharge
grade_boxplot(axes[0, 0], q_df, "n_years", "Years", "(a) Record length (Q)")
grade_boxplot(
    axes[0, 1],
    q_df,
    "mean_q_cms",
    "log₁₀(m³ s⁻¹)",
    "(b) Mean discharge",
    log_scale=True,
)
grade_boxplot(axes[0, 2], q_df, "q_cv", "CV", "(c) Discharge variability")

# Bottom row — Water levels (gauge-ID-excluded stations removed from paper-analysis scope)
lvl_no_hp = lvl_df[~lvl_df["is_hydropower"]]
n_hp = lvl_df["is_hydropower"].sum()
print(
    f"  Gauge-ID exclusion already removed {release_scope.n_excluded} release stations "
    "from level panels"
)
if n_hp:
    print(f"  Excluding {n_hp} additional hydropower stations from level panels")

grade_boxplot(axes[1, 0], lvl_no_hp, "n_years", "Years", "(d) Record length (H)")
grade_boxplot(axes[1, 1], lvl_no_hp, "mean_lvl_sm", "cm", "(e) Mean water level")
grade_boxplot(axes[1, 2], lvl_no_hp, "lvl_range", "cm", "(f) Level range")

fig.savefig(IMAGE_DIR / "fig_hydro_characteristics.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("Saved: fig_hydro_characteristics.png")

# Print discharge summary
print("\n=== Discharge Statistics by Grade ===")
print(
    q_df.groupby("grade")[["n_years", "mean_q_cms", "q_cv", "missing_pct"]].agg(
        ["count", "mean", "median"]
    )
)

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 3 — Data quality assessment  (Section 5.3)
# ══════════════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(2, 2, figsize=(14.0, 9.0), constrained_layout=True)

# (a) Grade distribution — grouped bar (Q vs H side by side)
grade_q = q_df["grade"].value_counts().reindex(GRADE_ORDER, fill_value=0)
grade_h = lvl_df["grade"].value_counts().reindex(GRADE_ORDER, fill_value=0)
x = np.arange(len(GRADE_ORDER))
w = 0.35

bars_q = axes[0, 0].bar(
    x - w / 2,
    grade_q.values,
    w,
    label="Discharge",
    color=[GRADE_COLORS[g] for g in GRADE_ORDER],
    edgecolor="black",
    linewidth=0.5,
)
axes[0, 0].bar(
    x + w / 2,
    grade_h.values,
    w,
    label="Levels",
    color=[GRADE_COLORS[g] for g in GRADE_ORDER],
    edgecolor="black",
    linewidth=0.5,
    alpha=0.5,
    hatch="//",
)
axes[0, 0].set_xticks(x)
axes[0, 0].set_xticklabels(GRADE_ORDER)
axes[0, 0].set_ylabel("Number of gauges")
axes[0, 0].set_title("(a) Grade distribution", fontsize=13, fontweight="bold", loc="left")
axes[0, 0].legend(fontsize=9, loc="upper right")
axes[0, 0].grid(alpha=0.15, axis="y", linestyle="--")

# Count labels on Q bars
for bar, val in zip(bars_q, grade_q.values, strict=False):
    if val > 50:
        axes[0, 0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 15,
            str(val),
            ha="center",
            fontsize=10,
        )

# (b) Missing data by grade — Q boxplots
q_missing = []
q_labels = []
for grade in GRADE_ORDER:
    vals = q_df[q_df["grade"] == grade]["missing_pct"].values
    if len(vals) > 0:
        q_missing.append(vals)
        q_labels.append(grade)

bp = axes[0, 1].boxplot(
    q_missing,
    tick_labels=q_labels,
    patch_artist=True,
    widths=0.6,
    flierprops={"markersize": 2, "alpha": 0.3},
    medianprops={"color": "black", "linewidth": 1.5},
)
for patch, grade in zip(bp["boxes"], q_labels, strict=False):
    patch.set_facecolor(GRADE_COLORS[grade])
    patch.set_alpha(0.7)
axes[0, 1].set_ylabel("Missing discharge data (%)")
axes[0, 1].set_title("(b) Data completeness", fontsize=13, fontweight="bold", loc="left")
axes[0, 1].grid(alpha=0.15, axis="y", linestyle="--")

# (c) Data type overlap — horizontal bar
ws_ids = set(ws.index.astype(str))
q_ids = set(q_df.index)
lvl_ids = set(lvl_df.index)
both_ids = q_ids & lvl_ids
q_only = q_ids - lvl_ids
lvl_only = lvl_ids - q_ids

overlap_labels = ["Q only", "Both Q & H", "H only"]
overlap_counts = [len(q_only), len(both_ids), len(lvl_only)]
overlap_colors = ["#4477AA", "#AA3377", "#228833"]

bars_ov = axes[1, 0].barh(
    overlap_labels,
    overlap_counts,
    color=overlap_colors,
    edgecolor="black",
    linewidth=0.5,
)
for bar, val in zip(bars_ov, overlap_counts, strict=False):
    axes[1, 0].text(
        bar.get_width() + 20,
        bar.get_y() + bar.get_height() / 2,
        str(val),
        va="center",
        fontsize=9,
        fontweight="bold",
    )
axes[1, 0].set_xlabel("Number of gauges")
axes[1, 0].set_title("(c) Variable overlap", fontsize=13, fontweight="bold", loc="left")
axes[1, 0].grid(alpha=0.15, axis="x", linestyle="--")

# (d) Summary table
ax_tbl = axes[1, 1]
ax_tbl.axis("off")

n_full = int(quality_df["has_full_coverage"].sum())
n_graded = int(quality_df["overall_grade"].notna().sum())

summary_data = [
    ["Release catchments", f"{release_scope.n_total:,}"],
    ["Paper-analysis catchments", f"{len(ws):,}"],
    ["Gauge-ID excluded", f"{release_scope.n_excluded:,}"],
    ["With discharge (Q)", f"{len(q_df):,}"],
    ["With water level (H)", f"{len(lvl_df):,}"],
    ["Both Q & H", f"{len(both_ids):,}"],
    ["Grade A (Q)", f"{int(grade_q.get('A', 0)):,}"],
    ["Full coverage 2008\u20132023", f"{n_full:,}"],
    ["Graded / discharge", f"{n_graded:,} / {len(q_df):,}"],
]

table = ax_tbl.table(
    cellText=summary_data,
    colLabels=["Metric", "Value"],
    loc="center",
    cellLoc="left",
)
table.auto_set_font_size(False)
table.set_fontsize(11)
table.auto_set_column_width([0, 1])
table.scale(1, 1.4)
for j in range(2):
    table[0, j].set_facecolor("#E0E0E0")
    table[0, j].set_text_props(fontweight="bold")

ax_tbl.set_title("(d) Dataset summary", fontsize=13, fontweight="bold", loc="left", pad=15)

fig.savefig(IMAGE_DIR / "fig_quality_assessment.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("Saved: fig_quality_assessment.png")

# ── Console summary ──────────────────────────────────────────────────────────
print("\n=== Data Coverage Summary (paper-analysis gauge-ID scope) ===")
print(f"Release watersheds: {release_scope.n_total}")
print(f"Gauge-ID excluded:  {release_scope.n_excluded}")
print(f"Watersheds:         {len(ws_ids)}")
print(f"With discharge:    {len(q_ids)}")
print(f"With levels:       {len(lvl_ids)}")
print(f"Both Q & H:        {len(both_ids)}")
print(f"Q only:            {len(q_only)}")
print(f"H only:            {len(lvl_only)}")
print(f"Full cov 2008-23:  {n_full}")
print(
    f"Q spatial coverage: {len(q_ids & ws_ids)}/{len(ws_ids)} "
    f"({len(q_ids & ws_ids) / len(ws_ids) * 100:.1f}%)"
)
print(f"\nAll figures saved to {IMAGE_DIR}")
