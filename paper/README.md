# CAMELS-RU Paper

**Target journal:** Earth System Science Data (ESSD)

## Structure

```
paper/
├── manuscript.md       # Full paper in GitHub-flavored Markdown
├── images/             # All figures (PNG)
├── latex/              # Original LaTeX source (for final ESSD submission)
│   ├── main.tex
│   ├── macros.tex
│   ├── refs.bib
│   ├── facts.yaml
│   ├── sections/
│   └── tables/
└── README.md           # This file
```

## Editing

Edit `manuscript.md` directly. GitHub renders it with full formatting (tables, math, images).

For collaborative review, use GitHub Pull Requests with line-level comments.

## Figures

All figures are in `images/`. Referenced in the manuscript as `![Figure N](images/filename.png)`.

Figures referenced in the manuscript:

| Figure | File | Description |
|--------|------|-------------|
| 1 | `fig_gauge_network.png` | Gauge network map + size distribution |
| 2 | `fig_quality_assessment.png` | Quality grade distribution |
| 3 | `fig_hydro_characteristics.png` | Discharge/water level characteristics |
| 4 | `fig_precip_comparison.png` | Precipitation spatial comparison |
| 5 | `fig_forcing_correlations.png` | Inter-dataset scatter plots |
| 6 | `fig_water_balance.png` | Runoff ratio and ET proxy |
| 7 | `fig_hydro_signatures_1.png` | Magnitude/baseflow signatures |
| 8 | `fig_hydro_signatures_2.png` | Timing/variability signatures |

Additional figures available in `images/` for supplementary material.

## Building LaTeX (for final submission)

```bash
cd latex/
latexmk -pdf main.tex
```

Requires: `copernicus.cls` (included), `booktabs`, `threeparttable`, `xspace`.

## Key Numbers

Dataset facts are in `latex/facts.yaml` and `latex/macros.tex`. When updating numbers in `manuscript.md`, also update these files for LaTeX consistency.
