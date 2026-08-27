# CAMELS-RU Paper

**Target journal:** Earth System Science Data (ESSD)

## Structure

```
paper/
├── overleaf/           # Active collaborative manuscript source (git submodule, Overleaf remote)
│   ├── main.tex
│   ├── macros.tex
│   ├── refs.bib
│   ├── sections/
│   └── tables/
├── images/             # Canonical manuscript figures, mirrored into overleaf/images/
├── tables/             # Data tables backing manuscript numbers (verify_macros.py audit trail)
└── README.md           # This file
```

(A legacy `paper/latex/` snapshot from the Markdown-era workflow may exist in local
working copies; it is gitignored and not authoritative.)

## Editing

The active collaborative manuscript source is the Overleaf submodule at `paper/overleaf/`.

Use Overleaf comments and nested-repo diffs for manuscript review. Use parent-repo pull requests for code, data-processing, release, and documentation changes.

## Figures

Canonical manuscript figures live in `paper/overleaf/images/`. Figure-generation scripts may write first to `paper/images/`; copy or script-sync any manuscript-used figure into `paper/overleaf/images/` before building or pushing Overleaf.

Figures referenced in the manuscript (in order of appearance; generators listed run
with `pixi run python`):

| File | Where | Description | Generator |
|------|-------|-------------|-----------|
| `fig_gauge_network.png` | §2 | Köppen–Geiger climate classes of the gauged catchments (forcing-derived) + catchment-size distribution | `scripts/regenerate_gauge_network_figure.py --write` |
| `fig_workflow.pdf` | §3 | Dataset production workflow schematic | `scripts/plot_workflow_schematic.py` |
| `fig_gauge_reliability.png` | §4 | Overall discharge grade + per-gauge share of Grade A years, mapped | `scripts/plot_gauge_reliability.py --write` |
| `fig_precip_comparison.png` | §7 | Precipitation-product differences | `scripts/regenerate_precip_comparison_figure.py --write` |
| `fig_budyko.pdf` | §7 | Budyko consistency check, one panel per product | `scripts/generate_budyko_figure.py` |
| `fig_coldregion_gradient.pdf` | §8 | Example cold-region signature analysis | `scripts/plot_coldregion_gradient.py` |
| `fig_hydro_signatures_1.png` … `_4.png` | Appendix | Signature maps, released cleaned set | `scripts/plot_signature_maps.py --write` |

Generators save each figure once and copy it to the second directory (`shutil.copy2`),
so `paper/images/` and `paper/overleaf/images/` stay byte-identical — verify md5 parity
before pushing Overleaf.

## Building the canonical manuscript

```bash
cd paper/overleaf
latexmk -pdf main.tex
```

Requires a TeX Live installation with the packages loaded in `main.tex` (`copernicus.cls` itself is included in the submodule).

## Key Numbers

Current manuscript numbers must be verified against `release/CAMELS_RU_v1.0/` and reflected in `paper/overleaf/macros.tex`. The older `paper/latex/` values are not authoritative.
