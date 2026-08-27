# CAMELS-RU — Cross-Agent Reference

**Companion to**: `AGENTS.md` (the cross-agent SoT). Lookup tables for Claude, Codex,
and Cursor. `CLAUDE_REFERENCE.md` imports this file (`@AGENTS_REFERENCE.md`).

---

## I. ENVIRONMENT

| Item | Value |
|------|-------|
| **Manager** | pixi (config in `pyproject.toml` → `[tool.pixi.*]`, no separate `pixi.toml`) |
| **Python** | 3.12 (`requires-python = ">=3.12"`) |
| **Formatter** | ruff format — line length 105, double quotes, docstring-code-format, docstring-code-line-length 72 |
| **Linter** | ruff check — rules: E, W, F, I, N, D, UP, B, S, C4, Q, T20, A, C90, PIE. Google docstrings. Max complexity 10. |
| **Type checker** | pyright (basic mode, Python 3.12, excludes `**/data`) |
| **Channel** | conda-forge |
| **Platform** | linux-64 |
| **GitHub** | HydroInformaticsRu/camels_ru |
| **Active branches** | `main` (default), `new_branch` (usual PR target) |
| **Paper target** | Earth System Science Data (ESSD); reverted from a brief HESS retarget |
| **Dataset license** | CC BY 4.0 (data), MIT (code) |

### Per-file lint relaxations (from `pyproject.toml`)

| Path | Relaxed rules |
|------|---------------|
| `tests/**/*` | S101, D100–D103, T20 |
| `scripts/**/*` | T20 (prints allowed) |
| `notebooks/**/*.py`, `**/*.ipynb` | D (docstrings), T20, S112 |

---

## II. PATHS

| Path | Purpose |
|------|---------|
| `src/hydro/` | Watershed delineation, discharge time series processing |
| `src/quality/` | Per-year quality grading (A–F); 21 flag types defined, 16 active in release-default grading |
| `src/meteo/` | Basin-averaged forcing from ERA5-Land, MSWEP v2.8, GPCP |
| `src/static/` | HydroATLAS attribute extraction (288 vars, 22 primary) |
| `src/timeseries_stats/` | 16 hydrological signatures (Table 3 in paper) |
| `src/data_processing/` | AIS GMVO XLS parsers, NetCDF builders |
| `src/plots/` | Paper figure generation (Albers Equal-Area Conic) |
| `src/utils/` | Shared helpers (logging, IO, transliteration) |
| `app/` | FastAPI web app for visual quality review (`app/main.py`) |
| `notebooks/` | Analysis notebooks (ruff: D, T20, S112 relaxed) |
| `scripts/` | CLI entry points (ruff: T20 relaxed) |
| `paper/overleaf/` | Active collaborative ESSD manuscript source (nested Overleaf git repo) |
| `paper/latex/` | Legacy generated LaTeX snapshot (local only, not shipped) |
| `paper/images/` | Reprojected figures for paper |
| `release/CAMELS_RU_v1.0/` | Zenodo release: NetCDF + CSV artifacts |
| `data/` | Symlink to external data root (not tracked, not on all machines) |
| `results/` | Intermediate analysis output |
| `logs/` | Runtime logs |
| `docs/` | Project documentation |

### `release/CAMELS_RU_v1.0/` contents

- `camels_ru_attributes.csv` — per-catchment HydroATLAS attributes
- `camels_ru_boundaries.gpkg` — catchment polygons
- `camels_ru_discharge.nc` — daily discharge (2,170 gauges, 2008–2023)
- `camels_ru_forcing.nc` — daily forcing (MSWEP P + ERA5-Land T + GLEAM4 PET)
- `camels_ru_gauge_summary.csv` — gauge metadata
- `camels_ru_signatures_summary.csv` — per-signature summary statistics
- `camels_ru_year_grades.csv` — per-year A–F grades
- `camels_ru_water_level.nc` — daily water level (2,989 gauges, BHS-77 datum + relative stage)

### Data root subdirectories (under `data/`)

| Path | Purpose |
|------|---------|
| `CAMELS_RU/` | Core dataset products |
| `Rasters/` | Gridded climate/terrain data |
| `Russia/` | Country-level shapefiles/boundaries |
| `World/` | Global reference layers (HydroATLAS, MERIT Hydro) |
| `zenodo/` | Staging area for release bundles |
| `Photos/`, `phd_data/`, `Transfer/`, `world_model/` | Auxiliary / archival |

---

## III. KEY NUMBERS

| Metric | Value |
|--------|-------|
| Catchments | 3,353 (manually verified) |
| Discharge gauges | 2,170 (936 Grade A, ~86% decent quality) |
| Water level gauges | 2,989 |
| Temporal coverage | 2008–2023 (daily) |
| Mean areal error | 5.1% (trimmed mean over \|err\| ≤ 100%; median 1.4%; n=3,011 with Roshydromet reference) |
| Grade A definition | Every assessed year Grade A |
| CRS for paper maps | Albers Equal-Area Conic |
| HydroATLAS attributes | 288 (22 primary subset) |
| Hydrological signatures | 16 metrics, 1,729 rows / 1,716 non-anomalous gauges (release CSV from `scripts/create_paper_signatures.py`, release-only inputs, complete hydro-years 2009–2023 at ≥ 70 % coverage, ≥ 5 valid years; MSWEP primary + `*_era5` variants; maps via `scripts/plot_signature_maps.py`) |
| Hydrological year | Oct–Sep |

---

## IV. FORCING SOURCES

| Variable | Source | Notes |
|----------|--------|-------|
| Precipitation (P) | MSWEP v2.8 | Basin-averaged |
| Temperature (T) | ERA5-Land | Basin-averaged |
| PET | GLEAM4 | Basin-averaged potential evapotranspiration |
| Reference (optional) | GPCP | Label fixed in commit 4aec076 (reviewer-requested) |

---

## V. KNOWN GOTCHAS

### `data/` symlink can break silently when the external drive is unplugged

- Symlink target: `/media/dmbrmv/ssd_2tb` (set at repo-root level)
- When the drive is unmounted, every path under `data/` fails to resolve, but scripts that
  write to `data/foo/bar.csv` may appear to succeed depending on error handling.
- Other drives (`SSD_DATA`, `hdd_data`) may be mounted and contain *stale* copies of the
  same layout — **do not substitute them silently**. A "successful" pipeline run on a stale
  input set corrupts downstream artifacts without failure signals.
- **Verify first**: `readlink data && ls "$(readlink data)" 2>&1 | head -3`. If the second
  command errors, stop and ask the user to remount before running any pipeline step that
  reads from `data/`.

### Copernicus float placement: a tall `[t]` figure defers every later figure to the end

- In `copernicus.cls` manuscript mode a `figure[t]` taller than roughly 70 % of the text
  height can never be placed, and LaTeX keeps every subsequent float queued behind it, so
  all remaining figures pile up after the references. Give tall figures `[tp]` (e.g. the
  two-panel `fig_gauge_reliability`) and check the figure pages after each build
  (`pdftotext -layout` per page, `pdftoppm` to view).
- Worse variant (found round 6): a `table` float taller than the page **silently drops
  its overflowing rows** — the build succeeds with only a "Float too large for page"
  log warning, and the page looks plausible. Two released-variable rows of the
  signatures table shipped un-rendered this way. Long tables go in `longtable`
  (already loaded), and after each build grep `main.log` for "Float too large" and
  count rendered rows against the source.
- Third variant (found round 10): full-page `[tp]` floats declared in the **last
  appendix** defer past `\dataavailability` and the other mandatory back-matter
  statements, interleaving appendix figures with them (Code availability was split
  across six pages). `\clearpage` at the end of the appendix (and of any
  figure-heavy section, e.g. §7) flushes the queue. Post-build check: no float may
  render after the "Data availability" heading.

### copernicus.cls renders `\correspondence` only if an `\Author` has a second bracketed argument

- `\correspondence{...}` alone just stores text; every render branch is gated on
  `\corr@cnt`, which advances only via `\Author[affil][email]{First}{Last}`. With
  plain `\Author[1]{...}{...}` the Correspondence line is **silently absent** from
  the PDF — no warning, and it shipped that way for nine review rounds. Post-build
  check: `pdftotext -f 1 -l 1 main.pdf - | grep Correspondence`.

### PostToolUse formatter strips a just-added import if it is momentarily unused

- The Edit hook runs ruff autofix after every edit. Adding an `import X` in one edit
  and the code that uses it in the next means the import is deleted between the two
  (seen twice with `shutil`/`sys`, 2026-08-24/25). Add the import in the same edit as
  its first use, or add the usage first and the import second.

### Figure scripts write to both image directories

- Every manuscript figure script writes to `paper/images/` **and** `paper/overleaf/images/`
  when run with `--write` (LaTeX reads only the latter via `\graphicspath`). Verify md5
  parity of the seven manuscript figures before pushing Overleaf; a stale copy in
  `paper/overleaf/images/` silently ships the old figure.
- Save the figure **once** and `shutil.copy2` it to the second directory: two consecutive
  `savefig(bbox_inches="tight")` calls crop a few pixels differently, so the two copies
  never agree byte-for-byte (seen 2026-08-23 on the signature maps).
