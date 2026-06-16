---
name: claude-md-audit
description: Audit the cross-agent instruction files (AGENTS.md + CLAUDE.md and their reference companions) for staleness, excess verbosity, and bad defaults. Use after repeated session-quality problems or when instruction files have drifted.
---

# Instruction-File Audit

Audit instruction files for quality, but keep the process practical. The goal is to improve operational behavior, not to produce a giant scorecard.

In camels_ru the rules are layered: `AGENTS.md` is the cross-agent source of truth (shared by Claude, Codex, Cursor); `CLAUDE.md` is a thin `@AGENTS.md` importer that adds only Claude-Code-only runtime sections. Lookup tables live in `AGENTS_REFERENCE.md`, imported via `CLAUDE_REFERENCE.md`. The audit must respect that layering.

## What To Check

- stale or contradicted facts (key numbers, paths, branch names, dataset counts)
- instructions that are too broad or too verbose
- rules that encourage drift, side work, or unverified claims
- duplicated instructions across the AGENTS layer and the CLAUDE layer
- **layering violations**: a shared rule written into `CLAUDE.md` instead of `AGENTS.md`, or Claude-only runtime detail leaking into `AGENTS.md`
- `CLAUDE.md` bloat — it should stay a thin importer, not re-state shared rules
- hooks/skills/settings that no longer match the written guidance

## Minimum Read Set

- `AGENTS.md` (the source of truth)
- `CLAUDE.md` (should be a thin `@AGENTS.md` importer)
- `AGENTS_REFERENCE.md` and `CLAUDE_REFERENCE.md`
- `.claude/settings.local.json` if present
- relevant hook or skill files only when needed

Do not default to broad project history unless the issue clearly depends on it.

## Output Format

```md
## Instruction-File Audit

### Findings
1. `path/to/file` — concise problem
   Why it matters: [1 sentence]
   Suggested change: [1 sentence — and where it belongs: AGENTS.md vs CLAUDE.md]

### Good Patterns To Keep
- [only if useful]

### Proposed Edits
- [small numbered list]
```

## Editing Rule

Prefer targeted edits, and **edit the source layer**:
- shared/cross-agent rules → `AGENTS.md` (or `AGENTS_REFERENCE.md` for lookup tables)
- Claude-only runtime detail → `CLAUDE.md` (keep it thin)
- remove stale facts; shorten overlong sections; add only project-specific operational rules

Do not introduce personality text, scoring systems, or broad framework rituals unless explicitly requested.

## Safety Rails

- Findings first, not scorecards first.
- Prefer fewer high-value edits over many cosmetic ones.
- Keep `CLAUDE.md` lean — a shared rule belongs in `AGENTS.md`, and lookup material belongs in the `*_REFERENCE.md` files.
