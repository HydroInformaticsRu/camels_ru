---
name: handoff
description: Use at session end to freeze context so the next /clear'd session resumes the HESS paper work without archaeology. Triggers: "handoff", "freeze context", "save session state", or the session is ending.
---

# Handoff

Freeze the current state so the next session picks up the HESS paper work cleanly. This repo has one context — finishing the dataset paper — so a handoff is a single, thorough end-of-session freeze (not a per-track operation).

Distinct from `/save`: `/save` is a quick mid-session checkpoint; `/handoff` is the thorough end-of-session freeze. The durable surfaces are the Claude auto-memory and git — reference those, nothing else.

## Process

### 1. Gather context

From this session, determine:
- **What we worked on** (the main task or change)
- **Where we left off** (exact stopping point)
- **Known debt** (deferred work, blocked items, "do this later" decisions — or "None")
- **Pick up from** (concrete next action: a command to run, a file to edit, a decision to make)

### 2. Write/update a `project`-type auto-memory entry

In `~/.claude/projects/-home-dmbrmv-Development-camels-ru/memory/`, keep a single living `project`-type memory that captures current paper state + next steps + known debt. Prefer **updating** the existing relevant entry (e.g. the paper-plan/state memory) over creating a new file.

Frontmatter convention:
```yaml
---
name: <short title>
description: <one line>
metadata:
  node_type: memory
  type: project
---
```
Then refresh the one-line index entry in `MEMORY.md`. Keep it short; no secrets or raw transcripts.

### 3. Ensure git is in a clean, described state

- `git status -sb` (parent) and `git -C paper/overleaf status -s` (manuscript submodule).
- If there are uncommitted changes, **suggest** a commit (with a concrete message) so the next session sees a described state — but do **not** auto-commit. The user commits.
- Note whether the parent is ahead of origin (unpushed) — a fresh session sees the remote-visible state.

### 4. Note manuscript state

Record the `paper/overleaf/` status in the handoff summary: clean vs N modified files, and whether the submodule pointer in the parent repo needs committing/pushing. The manuscript is canonical state.

### 5. Confirm

Print a short confirmation:

```
Handoff complete.
- Auto-memory: <file> updated (project state + next steps + known debt).
- Git (parent): <clean / N uncommitted — suggested commit: "<msg>">.
- Manuscript (paper/overleaf): <clean / N uncommitted>.
- Pick up from: <concrete next action>.
```

## Constraints

- No auto-commit and no force push — the user commits.
- No edits to the manuscript to "record" the handoff — state goes in auto-memory.
- Do not invent a `docs/sessions/` or initiative tree — auto-memory + git are the only surfaces.
- Keep it lean.
