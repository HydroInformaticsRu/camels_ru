# CAMELS-RU Paper

**Target journal:** Hydrology and Earth System Sciences (HESS)

## Structure

```
paper/
├── overleaf/           # Active collaborative manuscript source (nested Overleaf git repo; ignored by parent repo)
│   ├── main.tex
│   ├── macros.tex
│   ├── refs.bib
│   ├── sections/
│   └── tables/
├── manuscript.md       # Legacy Markdown snapshot/context; not canonical unless explicitly revived
├── images/             # Figure generation outputs mirrored into overleaf/images/ when used by the manuscript
├── latex/              # Legacy generated LaTeX snapshot from the Markdown-era workflow
│   ├── main.tex
│   ├── macros.tex
│   ├── refs.bib
│   ├── facts.yaml
│   ├── sections/
│   └── tables/
└── README.md           # This file
```

## Editing

The active collaborative manuscript source is the Overleaf git clone at `paper/overleaf/` in local working copies. Treat `manuscript.md` and `paper/latex/` as legacy Markdown-era context unless explicitly revived.

Use Overleaf comments and nested-repo diffs for manuscript review. Use parent-repo pull requests for code, data-processing, release, and documentation changes.

## Figures

Canonical manuscript figures live in `paper/overleaf/images/`. Figure-generation scripts may write first to `paper/images/`; copy or script-sync any manuscript-used figure into `paper/overleaf/images/` before building or pushing Overleaf.

Figures referenced in the manuscript:

| Figure | File | Description |
|--------|------|-------------|
| 1 | `fig_gauge_network.png` | Gauge network map + size distribution |
| 2 | `fig_quality_assessment.png` | Quality grade distribution |
| 3 | `fig_hydro_characteristics.png` | Discharge/water level characteristics |
| 4 | `fig_precip_comparison.png` | Precipitation spatial comparison |
| 5 | `fig_forcing_correlations.png` | Inter-dataset scatter plots |
| 6 | `fig_water_balance.png` | Runoff ratio and ET proxy |
| 7 | `fig_budyko.png` | Budyko consistency check |
| 8 | `fig_hydro_signatures_1.png` | Magnitude/baseflow signatures |
| 9 | `fig_hydro_signatures_2.png` | Timing/variability signatures |

Additional figures available in `images/` for supplementary material.

## Building the canonical manuscript

```bash
cd paper/overleaf
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

Current manuscript numbers must be verified against `release/CAMELS_RU_v1.0/` and reflected in `paper/overleaf/macros.tex`. The older `manuscript.md` and `paper/latex/` values are not authoritative.
