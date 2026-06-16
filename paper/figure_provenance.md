# CAMELS-RU HESS manuscript — figure provenance

Traceability map for the **12 figures** included in `paper/overleaf/` (verified against
the active `\includegraphics` calls in `sections/*.tex`). Written during the provenance
lock-down pass; figures were **not** regenerated (they compile and captions match content).
Regenerate a figure only if a number it depends on changes. Paths are relative to the repo root.

## Generator → figure map

The manuscript includes each figure from `paper/overleaf/images/`. Generators write to
`paper/images/` (notebooks) or to **both** `paper/images/` and `paper/overleaf/images/`
(the two scripts). Line numbers are the `savefig` call in the generator.

| Manuscript figure | Generator | Generator output filename | Kind |
|---|---|---|---|
| `fig_gauge_network.png` | `notebooks/00_DataDescription.py:381` | `fig_gauge_network.png` | notebook |
| `fig_quality_assessment.png` | `notebooks/00_DataDescription.py:570` | `fig_quality_assessment.png` | notebook |
| `fig_hydro_characteristics.png` | `notebooks/00_DataDescription.py:417` | `fig_hydro_characteristics.png` | notebook |
| `fig_hydro_signatures_1.png` | `notebooks/02_HydrologicalFinal.py:435` | `fig_hydro_signatures_1.png` | notebook |
| `fig_hydro_signatures_2.png` | `notebooks/02_HydrologicalFinal.py:456` | `fig_hydro_signatures_2.png` | notebook |
| `hydrograph_clusters_15.png` | `notebooks/02_HydrologicalFinal.py:331` | `fig_regime_hydrographs.png` ⚠ **renamed** | notebook |
| `hydro_clusters_15_map.png` | `notebooks/02_HydrologicalFinal.py:362` | `fig_regime_map.png` ⚠ **renamed** | notebook |
| `fig_precip_comparison.png` | `notebooks/03_ForcingsFinal.py:456` | `fig_precip_comparison.png` | notebook |
| `fig_water_balance.png` | `notebooks/03_ForcingsFinal.py:483` | `fig_water_balance.png` | notebook |
| `fig_forcing_correlations.png` | `notebooks/03_ForcingsFinal.py:564` | `fig_forcing_correlations.png` | notebook |
| `fig_budyko.png` | `scripts/generate_budyko_figure.py` | `fig_budyko.png` (writes both dirs) | script |
| `fig_coldregion_gradient.png` | `scripts/plot_coldregion_gradient.py` | `fig_coldregion_gradient.png` (writes both dirs) | script |

## Two regeneration paths

- **Scripts** (`fig_budyko`, `fig_coldregion_gradient`) — runnable directly, no approval:
  `pixi run python scripts/generate_budyko_figure.py` and
  `pixi run python scripts/plot_coldregion_gradient.py`. Both read committed-or-regenerable
  audit artifacts under `results/hess_quality/` (`budyko_per_gauge_product.csv`,
  `coldregion_robustness_strata.csv`, `aet_per_gauge_product.csv`) and write to **both**
  `paper/images/` and `paper/overleaf/images/`. Note `results/` is gitignored, so those
  inputs are local-only — regenerate via `scripts/hess_quality_audit.py` +
  `scripts/coldregion_robustness.py` if absent.
- **Notebooks** (the other 10 figures) — **require user approval** (long-running; project
  rule). `scripts/regenerate_paper_maps.py` is a convenience dispatcher that runs
  `notebooks/{00_DataDescription,02_HydrologicalFinal,03_ForcingsFinal}.py` as subprocesses.
  Notebooks write only to `paper/images/`.

## Two manual steps the generators do NOT perform

1. **Cluster-figure rename** (⚠ in the table above). Notebook 02 saves the §4 regime
   figures under their own names; the manuscript includes them under the cluster names:
   - `fig_regime_hydrographs.png` → `hydrograph_clusters_15.png`
   - `fig_regime_map.png` → `hydro_clusters_15_map.png`

   To regenerate, run notebook 02, then copy with the rename:
   ```bash
   cp paper/images/fig_regime_hydrographs.png paper/overleaf/images/hydrograph_clusters_15.png
   cp paper/images/fig_regime_map.png         paper/overleaf/images/hydro_clusters_15_map.png
   ```
2. **Image-dir sync.** The notebook figures land in `paper/images/` only; the manuscript
   reads `paper/overleaf/images/`. After regenerating any notebook figure, sync it:
   ```bash
   cp paper/images/<figure>.png paper/overleaf/images/<figure>.png
   ```
   (The two scripts already write both dirs, so they need no sync.)

## §4 clustering note

The featured §4 regime clustering (`hydrograph_clusters_15`, `hydro_clusters_15_map`) is the
**seasonal-hydrograph Ward clustering, k=15** in `notebooks/02_HydrologicalFinal.py`, run on
**1,443 gauges** (normalised 365-day median seasonal hydrograph; see the notebook's gauge
filter). This is distinct from the attribute-based clustering in
`notebooks/01_HydroAtlasFinal.py` (`paper/tables/cluster_assignments.csv`, "Cropland / Clay-rich"
names, n≈1,862), which is **not** the source of the regime figures.
