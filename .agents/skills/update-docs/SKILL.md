---
name: update-docs
description: Update only the documentation directly affected by completed work. Use when the user asks to update docs, save session learnings, or record a completed change.
user-invocable: false
---

# Documentation Update Protocol

This skill is for scoped documentation maintenance, not broad autonomous doc rewriting.

## Core Rule

Update only the smallest set of documents needed to record the completed work.

Do not:
- rewrite broad progress/history files without need
- touch the manuscript to record process/state changes (the paper is the scientific source of truth; record process elsewhere)
- invent project-state changes that were not verified

## Preferred Targets

Choose the narrowest relevant target:

1. Agent rules (only when a *rule* genuinely changed)
   - `AGENTS.md` / `AGENTS_REFERENCE.md` — shared cross-agent rules (the source of truth)
   - `CLAUDE.md` / `CLAUDE_REFERENCE.md` — Claude-only runtime layer (keep `CLAUDE.md` thin)

2. Project docs
   - `README.md` — only when the change affects the public-facing summary
   - `docs/` — the relevant existing doc (e.g. an execution-plan or readiness file), not a new tree

3. Manuscript-adjacent notes
   - only a note *about* the manuscript work, never an in-place scientific edit to `paper/overleaf/` made to "record" something

## What To Record

- what changed
- why it mattered
- where the durable record should live
- any verified next step

Keep entries short and factual.

## Process

1. Identify the exact completed work.
2. Choose the minimum doc set that should reflect it.
3. Verify the code/test/figure/manuscript evidence first.
4. Update those docs only.
5. Do not branch into unrelated "while here" doc cleanup.

## Output

When reporting back, say:

```md
Updated:
- [doc path] — [1 line reason]

Not updated:
- [doc path] — [why it was intentionally left alone]
```

## Safety Rails

- No automatic updates just because "something changed."
- No edits to `paper/overleaf/` to record state — that's continuity (`/save`, `/handoff`, auto-memory), not documentation.
- No broad rule rewrites without a verified rule change; shared rules belong in `AGENTS.md`.
