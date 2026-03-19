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

## Review History

The manuscript went through 4 rounds of automated peer review (4 independent Opus agents + Codex second opinion per round):

| Round | Score | Key fixes |
|-------|-------|-----------|
| R1 | 74 | Strict Grade A, per-year mask, paper→markdown |
| R2 | 72 | β corrected (0.824→0.290), Q/P >1 fixed, GRDC added, sensitivities |
| R3 | 89 | Missing Linke ref, flag count, grading logic, grammar |
| R4 | 91 | Ref ordering, rounding, verb fragments, symbol clash |

## Key Numbers

All numbers in `manuscript.md` were verified against source code and recomputation on 2026-03-19. The LaTeX source in `latex/` is a snapshot from the original conversion; `manuscript.md` is the source of truth.
