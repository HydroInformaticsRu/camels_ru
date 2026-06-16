# CAMELS-RU — Claude Code Runtime Layer

> **Cross-agent rules (Claude, Codex, Cursor) live in `@AGENTS.md` — the source of truth.**
> This file imports it and adds only Claude-Code-only runtime sections. Lookup tables
> live in `@CLAUDE_REFERENCE.md` (which imports `AGENTS_REFERENCE.md`).
> **Edit a *shared* rule in `AGENTS.md`, not here.**

@AGENTS.md

@CLAUDE_REFERENCE.md

---

## Startup

1. Cross-agent rules and the file-system map are imported above from `AGENTS.md`;
   lookup tables from `CLAUDE_REFERENCE.md` → `AGENTS_REFERENCE.md`.
2. Check `git status` for current state.
3. Verify what needs to be done before making changes.

**This repo has one track: finish the HESS paper.** Treat manuscript progress
(`paper/overleaf/`), the dataset release, and the auto-memory below as the durable state —
there is no multi-track scaffolding here.

## Skills (invoke via the Skill tool)

When the user types `/<skill-name>`, invoke it via the `Skill` tool — don't guess names.
Project-relevant skills:

- **Research writing** — `/science-buddy` (drafting, revision, academic writing),
  `/science-reviewer` (adversarial peer review), `/science-judge` (buddy + reviewer
  refinement loop).
- **Continuity (single-track, paper-oriented)** — `/save` (lightweight session
  checkpoint → memory + session note), `/status` (git + paper-progress dashboard),
  `/kickoff` (paste-ready prompt to resume in a fresh session), `/handoff` (end-of-session
  context freeze), `/update-docs` (scoped doc maintenance), `/claude-md-audit` (audit
  CLAUDE.md / AGENTS.md for staleness).
- **Knowledge graph** — `/graphify` (any input → knowledge graph; treat questions about
  the codebase/docs as graphify queries when `graphify-out/` exists).

## Memory

Persistent auto-memory lives at
`~/.claude/projects/-home-dmbrmv-Development-camels-ru/memory/` (`MEMORY.md` index + one
fact per file). Check it at session start; write durable, non-obvious project facts there
(not what the repo/git already records). This is Claude-side; Codex keeps its own private
memory at `~/.codex/MEMORY.md`.

## Subagent & model discipline

- Delegate aggressively to subagents (Explore for codebase searches, general-purpose for
  bounded research/review) — they carry their own model and don't burn main-thread tokens.
- For cross-vendor review, use the federation gate (`federation-advisor`, `ask-codex`,
  `ask-cursor`) as described in `AGENTS.md` § Cross-Agent Federation.
