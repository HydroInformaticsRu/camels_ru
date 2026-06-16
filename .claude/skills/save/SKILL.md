---
name: save
description: >-
  Use when the user says "save", "/save", "save this session", "checkpoint", or
  "freeze context". Records a lightweight continuity checkpoint: updates the
  Claude auto-memory when a durable fact emerged, and summarizes git state so the
  next session resumes the paper work without archaeology.
---

# Save

Create a continuity checkpoint. This is a quick *mid-session* checkpoint — lighter than `/handoff` (the thorough end-of-session freeze). Optimize for making the next session feel like it remembers the work.

## Workflow

1. Inspect current state (read-only):
   - `git status --short` (parent repo)
   - `git -C paper/overleaf status -s` (manuscript submodule)
   - the most recent committed plan/doc and open todos, if any

2. Update the Claude **auto-memory** when (and only when) a durable, non-obvious fact emerged that git/the repo doesn't already record. Memory dir:
   `~/.claude/projects/-home-dmbrmv-Development-camels-ru/memory/`
   - One fact per file. Frontmatter convention:
     ```yaml
     ---
     name: <short title>
     description: <one line>
     metadata:
       node_type: memory
       type: project   # one of: user | feedback | project | reference
     ---
     ```
   - Pick the `type`: `user` (work-style preference), `feedback` (a correction to apply), `project` (state/decision about this paper/dataset), `reference` (durable lookup fact).
   - Then add or refresh the one-line index entry in `MEMORY.md`.
   - Keep entries short and generalizable. No secrets, raw transcripts, credentials, or private data.

3. If nothing durable emerged, skip the memory write — a `/save` can be just a git-state summary. Do not manufacture a memory.

4. Optional human-readable note: if the user wants one, suggest appending a short note to an **existing** doc under `docs/` (e.g. the relevant execution-plan file). Do not invent a `docs/sessions/` or session-tree.

5. Do not commit, push, edit the manuscript, or touch unrelated files unless the user explicitly asks. This skill does **not** auto-commit.

## Final Response

Report:
- whether auto-memory was updated (and which file), or why not
- a one-line git-state summary (parent + `paper/overleaf`)
- any save limitations
- the shortest practical resume command or next action
