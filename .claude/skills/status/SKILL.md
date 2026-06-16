---
name: status
description: Quick project health dashboard for camels_ru. Use when user says "project status", "show status", "what's the state", "health check", or wants a snapshot of git, the manuscript, and current focus.
argument-hint: ""
---

# Project Status Dashboard

You are generating a concise project health snapshot for camels_ru. This repo has one focus: finishing the HESS dataset paper. The durable state is git, the auto-memory, and the manuscript (`paper/overleaf/`, a nested git repo).

## Pre-Computed Context

!`$(git rev-parse --show-toplevel)/.claude/skills/status/scripts/gather-status.sh`

## Process

### 1. Analyze Pre-Computed Data

From the pre-gathered context above, extract:
- **Branch**: current branch name and tracking status
- **Uncommitted changes**: count and summary (parent repo)
- **Recent commits**: last 3-5 messages
- **Manuscript state**: `paper/overleaf/` git status and recent commits (it is a nested repo with its own history)

### 2. Read Additional Context (if needed)

If the manuscript block is unclear, you may run `git -C paper/overleaf status -s` directly. Check the open TodoWrite/task list for the current focus if one exists.

### 3. Generate Dashboard

Output a **concise** dashboard. No ASCII box art. Use markdown tables and headers:

```markdown
## CAMELS-RU Status

**Branch**: `main` (ahead 2, behind 0)
**Uncommitted**: 5 files modified, 2 untracked

### Manuscript (paper/overleaf)
- Overleaf repo: clean / N files modified
- Recent: `abc1234` <message>

### Recent Commits (parent repo)
- `abc1234` fix: description
- `def5678` feat: description

### Health
| Check | Status |
|-------|--------|
| Git (parent) | Clean / N uncommitted |
| Manuscript (overleaf) | Clean / N uncommitted |

### Current Focus
[the open TodoWrite/task focus if any, else "see most recent commit / auto-memory"]

### Suggested Actions
- [contextual action based on actual state]
```

### 4. Contextual Suggestions

Based on actual state, suggest **only relevant** next actions:

| Condition | Suggestion |
|-----------|-----------|
| Uncommitted changes in parent | "Consider committing or running `/save`" |
| Uncommitted changes in `paper/overleaf` | "Commit/push the Overleaf submodule before `/clear`" |
| Behind remote | "Pull latest: `git pull`" |
| Session ending | "Run `/handoff` to freeze context for the next session" |

Only suggest 1-3 actions. Don't list actions for conditions that don't apply.

## Constraints

- This is **read-only** — do not modify any files
- Keep output **under 40 lines** — this is a quick status check
- No dependency audits or test runs — those are separate
- Use actual data from pre-computed context, not templates
