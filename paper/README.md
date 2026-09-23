# CAMELS-RU manuscript and figures

The canonical manuscript for *Earth System Science Data* is the nested Overleaf
repository at `paper/overleaf/`. Its Git revision is recorded by the parent
repository. Access to the Overleaf remote may require project credentials; cloning
the public processing repository does not establish anonymous manuscript access.

## Manuscript source and build

For collaborators with Overleaf Git access, run from the repository root:

```bash
git submodule update --init paper/overleaf
mkdir -p .tmp/manuscript
cd paper/overleaf
latexmk -pdf -outdir=../../.tmp/manuscript main.tex
```

TeX Live and `latexmk` are required. The Copernicus class and bibliography style
are included. Inspect the compiled PDF as well as the log for undefined references,
overfull boxes, and oversized floats. Figures must appear before Data availability.

## Scientific assets

| Directory | Purpose |
|---|---|
| `overleaf/sections/`, `overleaf/tables/` | Manuscript text and LaTeX tables |
| `overleaf/refs.bib`, `overleaf/macros.tex` | Bibliography and numerical macros |
| `images/`, `overleaf/images/` | Matching copies of manuscript figures |
| `figures_src/` | Workflow-diagram source |
| `figure_data/hex_support/` | Grid definition, cell statistics, and gauge membership for current hex maps |
| `tables/` | Scientific tables supporting manuscript values |
| `metadata/` | Release documentation, interoperability crosswalks, and validation record |

## Figure generation

Commands below run from the repository root with `pixi run python`. They require
the source inputs referenced by each script. The national basemap also uses
external terrain/river products. Do not execute all notebooks to rebuild figures.

| Figure | File | Generator |
|---|---|---|
| 1 | `fig_gauge_network.png` | `scripts/regenerate_gauge_network_figure.py --write` |
| 2 | `fig_workflow.pdf` | `paper/figures_src/fig_workflow.tex`; build command in its header |
| 3 | `fig_gauge_reliability.png` | `scripts/plot_gauge_reliability.py --write` |
| 4 | `fig_grading_examples.pdf` | `scripts/plot_grading_examples.py --write` |
| 5 | `fig_precip_comparison.png` | `scripts/regenerate_precip_comparison_figure.py --write` |
| 6 | `fig_budyko.pdf` | `scripts/generate_budyko_figure.py` |
| 7 | `fig_coldregion_gradient.pdf` | `scripts/plot_coldregion_gradient.py` |
| B1–B4 | `fig_hydro_signatures_1.png` through `_4.png` | `scripts/plot_signature_maps.py --write` |

The map scripts without `--write` produce local previews. Budyko and cold-region
scripts always update both image directories and their supporting tables;
precipitation previews also update `tables/precip_comparison_caption.csv`.
`scripts/regenerate_paper_maps.py` is a legacy notebook runner, not the figure build
entry point. Keep plotting caches and temporary files under the project `.tmp/`.

Climate, precipitation-difference, and signature maps use a fixed-origin Albers
hexagon grid with a 66 km centre-to-vertex radius. Continuous values use cell
medians; climate uses the most frequent displayed class. Histograms count original
gauges. Figure 3 retains individual gauge points. Section 2.4 of the manuscript and
[the figure-data README](figure_data/hex_support/README.md) describe the calculation
and its limits. Figure 4 shows released runoff, precipitation, and annual grades
for gauges 19128 and 75387; it does not recompute the grading algorithm.

Each generator saves once and copies its figure to the second image directory.
Check that all eleven pairs are byte-identical before updating the manuscript.

## Numerical verification and release scope

With the baseline package present:

```bash
pixi run python scripts/verify_macros.py --release-dir release/CAMELS_RU_v1.0
```

This checks manuscript macros against release values and retained scientific audit
tables. It verifies numerical consistency, not independent observational accuracy.
The default figure inputs remain the frozen v1.0 package. Applicability to the
separate CF-1.9 metadata candidate rests on complete numerical-preservation checks;
see [metadata/VALIDATION.md](metadata/VALIDATION.md).

The dataset packages are not stored in Git. Internal editorial reviews, companion
working drafts, preview PDFs, and build logs remain local. Scientific methods,
references, figure support, and reproducibility checks remain tracked.
