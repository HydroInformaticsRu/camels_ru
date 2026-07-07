# CAMELS-RU Paper

**Target journal:** Earth System Science Data (ESSD)

## Structure

```
paper/
├── overleaf/           # Active collaborative manuscript source (nested Overleaf git repo; ignored by parent repo)
│   ├── main.tex
│   ├── macros.tex
│   ├── refs.bib
│   ├── sections/
│   └── tables/
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

The active collaborative manuscript source is the Overleaf git clone at `paper/overleaf/` in local working copies. Treat `paper/latex/` as legacy Markdown-era context unless explicitly revived.

Use Overleaf comments and nested-repo diffs for manuscript review. Use parent-repo pull requests for code, data-processing, release, and documentation changes.

## Figures

Canonical manuscript figures live in `paper/overleaf/images/`. Figure-generation scripts may write first to `paper/images/`; copy or script-sync any manuscript-used figure into `paper/overleaf/images/` before building or pushing Overleaf.

Figures referenced in the manuscript:

| Figure | File | Description |
|--------|------|-------------|
| 1 | `fig_gauge_network.png` | Gauge network map + catchment-size distribution (§2) |
| 2 | `fig_gauge_reliability.png` | Per-gauge share of Grade A years, mapped (§4) |
| 3 | `fig_hydro_signatures_1.png` | Magnitude/baseflow signatures (§5) |
| 4 | `fig_hydro_signatures_2.png` | Timing/variability/extreme signatures (§5) |
| 5 | `fig_precip_comparison.png` | Precipitation-product differences (§6) |
| 6 | `fig_budyko.png` | Budyko consistency check (§6) |
| 7 | `fig_coldregion_gradient.png` | Example cold-region signature analysis (§8) |

Additional figures available in `images/` for supplementary material.

## Building the canonical manuscript

```bash
cd paper/overleaf
latexmk -pdf main.tex
```

Requires: `copernicus.cls` (included), `booktabs`, `threeparttable`, `xspace`.

## Key Numbers

Current manuscript numbers must be verified against `release/CAMELS_RU_v1.0/` and reflected in `paper/overleaf/macros.tex`. The older `paper/latex/` values are not authoritative.
