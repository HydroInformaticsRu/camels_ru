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
| `fig_workflow.pdf` | §3 | Dataset production workflow schematic | `paper/figures_src/fig_workflow.tex` (standalone TikZ; build line in its header) |
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

## ESSD revision, 23 September 2026

The review trail is in `paper/reviews/ESSD_REVISION_LOG_2026-09-23.md`; the original
review and approved plan are archived beside it. This is a local author-review
revision, with submission gates still open. `release/CAMELS_RU_v1.0/` is the frozen
numerical baseline. The local v1.1 amendment preserves its existing numerical
variables and files while adding station coordinates, interoperability metadata and
reuse guidance. Do not retarget the DOI to a version that has not been released.

Metadata sources live in `paper/metadata/`. The amendment command and complete
verification sequence are in the archived plan. The macro verifier accepts
`--release-dir`; the default stays v1.0. Figure generators retain the frozen baseline
inputs; candidate applicability requires the complete release-equivalence report.

Figure execution has side effects: precipitation previews also write
`paper/tables/precip_comparison_caption.csv`; Budyko and cold-region generators always
write both image trees and their provenance tables. Do not use
`scripts/regenerate_paper_maps.py`, which executes legacy notebooks. Regenerate only
the explicitly listed figures.

The preferred local candidate, `release/CAMELS_RU_v1.1_cf19/`, passes complete
numerical-equivalence and strict CF-1.9 checks on all three NetCDFs. It renames the
instance dimension to `station`, retaining string `gauge_id(station)`; the shared
loading helper supports either schema. See `paper/reviews/CF19_VALIDATION_2026-09-23.md`.
The first candidate and its failed CF-1.8 checks remain preserved separately.
No candidate has been archived or assigned a new DOI.
