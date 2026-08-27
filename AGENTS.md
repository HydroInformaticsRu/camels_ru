# CAMELS-RU — Cross-Agent Operating Rules

> **Canonical source of truth (SoT) for every coding agent — Claude, Codex, Cursor.**
> Shared rules and conventions live here, once. `CLAUDE.md` imports this file
> (`@AGENTS.md`) and adds Claude-Code-only runtime sections; `.cursor/rules/camels-ru.mdc`
> and `~/.codex/AGENTS.md` point here. Lookup tables (paths, environment, key numbers,
> forcing sources, gotchas) live in **`AGENTS_REFERENCE.md`**.
> **Edit a shared rule here — nowhere else.**

---

## Overview

**CAMELS-RU** — a CAMELS-standard hydroclimatic dataset for 3,353 Russian catchments
(daily discharge, water level, ERA5-Land/MSWEP/GLEAM forcing, HydroATLAS attributes,
2008–2023). Target journal: **Earth System Science Data (ESSD)**; the paper is a data
description article, so it needs data-descriptor framing (reusability, provenance, and
validation) rather than a hydrological-analysis narrative. Relocated analysis lives in
`paper/overleaf/COMPANION_DRAFT.md` for a separate companion paper.

**Stack**: Python 3.12 / pixi / ruff / pyright / xarray + NetCDF / GeoPandas / FastAPI
(quality-review app) / LaTeX (manuscript).

This is a **dataset + manuscript** repository, not a modeling/calibration codebase.

---

## Working Conduct (all agents — Claude, Codex, Cursor)

1. **Ask, don't assume.** If something is unclear, ask before writing a single line.
   Never make silent assumptions about intent, architecture, or requirements.
2. **Simplest solution first.** Implement the simplest thing that could work; no
   abstractions or flexibility that weren't explicitly requested.
3. **Don't touch unrelated code.** If a file or function isn't part of the current
   task, leave it — even if you think it could be improved.
4. **Flag uncertainty explicitly.** Say so before proceeding when you're not confident;
   confidence without certainty causes more damage than admitting a gap.
5. **Verify before asserting.** If code, config, logs, or a command can resolve a
   factual claim, check first. Stale memory and hallucinated APIs have real cost.

---

## Process Workflow (superpowers)

The **superpowers** plugin is **cross-platform** — Claude, Codex, and Cursor all run it.
It supplies the default *process* skills. Prefer these broad, maintained skills over
bespoke per-repo rules, and invoke them by their trigger:

| Trigger | superpowers skill |
|---------|-------------------|
| Non-trivial feature / change | `brainstorming` → `writing-plans` → `executing-plans` |
| Any bug, test failure, "why is X happening?" | `systematic-debugging` — root cause **before** any fix |
| New or changed logic | `test-driven-development` — write the failing test first |
| Before declaring anything "done" | `verification-before-completion` — run the check the user would |
| Giving / getting code review | `requesting-code-review` / `receiving-code-review` |
| Branch lifecycle | `using-git-worktrees`; `finishing-a-development-branch` |

For research-writing tasks, the global science skills apply across agents:
`science-buddy` (drafting/revision), `science-reviewer` (adversarial peer review),
`science-judge` (buddy + reviewer refinement loop).

---

## Cross-Agent Federation

This repo participates in the global agent federation (`~/.agent-federation/`). The
machinery is global; the binaries already work from this directory.

**Default operating rule:** the user states a goal; the lead agent chooses tools, skills,
and external reviewers. For meaningful hydrology, statistical, manuscript-claim, or
agent-tooling work, run the policy gate:

```bash
~/.agent-federation/bin/federation-advisor --cwd "$PWD" "<task/claim>"
```

If it says external review is warranted, either add `--run`, or call `ask-codex` /
`ask-cursor` directly with the generated prompt. **Reviewers are read-only and advisory**;
the lead agent synthesizes and verifies. Do **not** resolve by consensus — truth is
resolved by evidence, deterministic checks, and source references.

**Codex shell safety** (Codex has no per-call bash hook; honor as hard rules): never run
filesystem wipes (`rm -rf /`, `rm -rf ~`/`$HOME`, `rm -rf data/`), disk/format tools
(`mkfs`, `dd if=`), history rewrites / force ops (`git push --force`, `git reset --hard`)
unless explicitly asked, privilege escalation (`sudo`), or writes to system `/tmp`.
Use `rm -r` on a specific, verified path — never `rm -rf`.

---

## Immutable Rules

| Rule | Meaning |
|------|---------|
| **No `/tmp`** | All temp files in project `data/` or a project-level `.tmp/`. Never system `/tmp`. |
| **No placeholders** | `<region>`, `[PATH]`, `TBD` in code → ask for real values or fail explicitly. |
| **CRS validation** | Always check `.crs` before spatial ops (`to_crs`, `clip`, `intersection`, `sjoin`, reproject). Mismatch causes silent wrong results. Paper maps use Albers Equal-Area Conic (commit 74c30ca). |
| **Use `pixi run`** | Run scripts with `pixi run python <script.py>`, not bare `python`. Pixi config lives in `pyproject.toml` under `[tool.pixi.*]` (no separate `pixi.toml`). |
| **Ask before running notebooks** | Notebooks in `notebooks/` can be long-running and produce figures. Confirm target and scope before executing. |
| **No fabricated citations** | Never invent references in `paper/`. Tag `[CITE]` for the user to fill. |
| **Respect Grade-A definition** | A gauge is Grade A only if *every* assessed year is Grade A. Do not relax this. |
| **Keep `src/` lint-clean** | `src/` was fully cleaned (commit 4118bfb). Do not reintroduce ruff violations. Notebooks/scripts have relaxed rules (see `pyproject.toml`). |
| **Missing data = `np.nan`** | Never sentinels (`0`, `-9999`, `999.99`). Units explicit: discharge m³/s, area km². |

---

## File System Map

```text
camels_ru/
├── src/                       # Python package (camels-ru), lint-clean
│   ├── hydro/                 # Watershed delineation, discharge processing
│   ├── quality/               # Quality grading (A–F), flag logic
│   ├── meteo/                 # Forcing aggregation (ERA5-Land, MSWEP, GPCP)
│   ├── static/                # HydroATLAS attribute extraction
│   ├── timeseries_stats/      # Hydrological signatures
│   ├── data_processing/       # Pipeline glue (AIS GMVO parsers, NetCDF builders)
│   ├── plots/                 # Paper figures, map reprojection (Albers Equal-Area Conic)
│   └── utils/                 # Shared helpers
├── app/                       # FastAPI quality-review web app
├── notebooks/                 # Analysis notebooks (long-running — ask first)
├── scripts/                   # CLI entry points (parsers, builders, graders)
├── paper/                     # ESSD manuscript
│   ├── overleaf/              # Active manuscript source (nested Overleaf git repo)
│   ├── latex/                 # Legacy generated LaTeX snapshot
│   ├── images/                # Figures (Albers Equal-Area Conic)
│   └── tables/                # Data tables
├── release/CAMELS_RU_v1.0/    # Zenodo release artifacts (NetCDF + CSV) — ask before editing
├── results/                   # Intermediate analysis output
├── data/                      # Symlink to external data (not tracked; may be unplugged)
├── docs/                      # Project documentation
└── logs/                      # Runtime logs
```

Full path table, environment, key numbers, forcing sources, and gotchas:
**`AGENTS_REFERENCE.md`**.

---

## CLI & Workflow

```bash
# Environment
pixi install                       # Install dependencies (Python 3.12, linux-64, conda-forge)
pixi run python <script.py>        # Run with pixi env
pixi shell                         # Drop into env shell

# Code quality (pixi tasks defined in pyproject.toml)
pixi run lint                      # ruff check src/
pixi run format                    # ruff format src/
pixi run typecheck                 # pyright src/
for t in tests/test_*.py; do pixi run python "$t"; done   # self-checking test scripts (what CI runs)

# Pipeline (typical order)
python scripts/ParseAis*.py               # AIS GMVO (XLS) → compound CSVs
python scripts/aggregate_watersheds.py    # forcing → per-gauge
python scripts/GradeCompound.py           # quality grading (A–F)
python scripts/create_year_grades.py      # year_grades.csv
python scripts/create_forcing_netcdf.py   # forcing NetCDF
python scripts/package_dataset.py         # discharge/water-level NetCDF + Zenodo bundle
```

---

## Decision Hierarchy

When sources conflict, higher rank wins:

1. `paper/overleaf/` — canonical collaborative manuscript source (reviewer-facing ESSD LaTeX)
2. **`AGENTS.md`** — cross-agent behavioral rules (this file; the SoT)
3. `CLAUDE.md` — Claude-Code-only runtime layer (imports this file)
4. `AGENTS_REFERENCE.md` — technical details
5. `README.md` — public-facing summary
6. Training knowledge — lowest priority

---

## Permission Levels

**Always ask before**:
- File deletion (notebooks, scripts, paper sections)
- `git push --force` or push to `main` / `new_branch`
- Modifying `release/CAMELS_RU_v1.0/` (Zenodo artifacts)
- Running long notebooks (`notebooks/`)
- Adding new dependencies (updates `pyproject.toml`)
- Operations estimated >10 min

**Never do without approval**: delete files, force push, modify `.git/` or `.claude/`,
run `sudo`, or edit the paper in ways that change scientific claims without a review trail.

---

## Domain Deference

Apply engineering judgment to: code, architecture, config, pipelines, dependencies.
Defer to the user on: hydrology decisions, quality-grading thresholds, metric selection,
research direction, and manuscript scientific claims — unless there's a clear
software-engineering concern.

---

## Error Recovery

| Class | Action |
|-------|--------|
| **Import error** | Is the pixi env active (`pixi shell`)? Is the import path correct (first-party modules: `hydro`, `meteo`, `quality`, `data_processing`, `plots`, `static`, `timeseries_stats`, `utils`)? |
| **CRS mismatch** | Reproject explicitly before the spatial op. Paper maps use Albers Equal-Area Conic. Check `.crs` on every GeoDataFrame. |
| **Data not found** | Ask the user for data location. Do not fabricate paths. `data/` is a symlink — may not exist or may be unplugged (see `AGENTS_REFERENCE.md` § Gotchas — verify before any pipeline run). |
| **Lint / type failure** | Fix the issue; don't disable the rule without asking. `src/` is lint-clean as of commit 4118bfb. |
| **Test failure** | Diagnose root cause before attempting a fix. |
| **Notebook taking too long** | Stop, report, ask. Don't silently rerun on a subset. |

When something fails: stop, report the error, explain what you know, propose a fix.
Do not silently retry or continue past failures.
