---
name: kickoff
description: Use when you need a paste-ready prompt to start a FRESH (/clear'd) Claude Code session that continues the HESS paper work from committed artifacts — common in terminal-only / no-IDE setups where one session crafts a plan and the next runs it. Triggers: "kickoff prompt", "prompt for fresh/next session", "prompt to continue", "handoff prompt to paste", "give me a prompt to resume".
---

# kickoff — generate a fresh-session kickoff prompt

## Overview

Produce a **self-contained** prompt the user pastes into a fresh `/clear`'d session so it can continue the HESS paper work with **zero memory of the crafting conversation**. The prompt must work from committed artifacts + auto-memory ALONE.

Core principle: **point at durable artifacts, verify state, don't guess.** Reference committed files (don't re-inline them — that drifts), and make every concrete fact (branch, what's done, manuscript state) *verified from the repo*, not recalled from the conversation.

This repo has one context: **finishing the HESS dataset paper.** There is no multi-track scaffolding to reference.

## When to use
- User is about to `/clear` and continue the paper work in a new session.
- Terminal-only / no-IDE handoff; the recurring "give me a prompt for next session."
- Right after crafting a plan, roadmap, or analysis a later session will execute.

**Not for:** persisting session state (use `/handoff` or `/save`); executing a plan now (use `superpowers:executing-plans`).

## Procedure

1. **Identify the target.** Use the path the user gave. Otherwise: the most recent committed plan/roadmap if one exists (e.g. under `docs/`), else reconstruct the resume point from `git log`, the open todos, and the manuscript state (`paper/overleaf/`). **Read whatever you point at** — the prompt must match its actual structure.

2. **Verify state from the repo — never guess** (the #1 failure is writing the *wrong branch* from stale recall):
   - `git branch --show-current` → the branch to write in Setup.
   - If pointing at a plan file: `git log --oneline -1 -- <plan-file>` → confirm it is **committed**.
   - `git status -sb` → confirm tree clean and **not ahead** of origin (i.e. pushed).
   - `git -C paper/overleaf status -s` → confirm the manuscript submodule is committed/pushed if the next session depends on it.
   - If any referenced artifact is uncommitted/unpushed: **commit + push first**, or the fresh session can't rely on it. A fresh session sees the repo, not your conversation.

3. **Catch session-only facts.** Anything discovered this conversation that the fresh session needs but is NOT in a committed artifact → write it into the artifact or auto-memory first (preferred), or state it explicitly in the prompt. Recalled `<system-reminder>` memory is background, not a substitute.

4. **Pick the run mode** → shapes the "how to run" section:
   - **Committed plan/roadmap exists**: tell it to read that plan and resume at the first open step.
   - **No plan, reconstruct**: tell it to read the latest commits + open todos + `paper/overleaf/` state, then continue the paper work directly.
   - **Design/analysis needing a plan**: tell it to invoke `superpowers:writing-plans`, then execute.

5. **Assemble** with the template below. Output **only** the prompt in a code block (paste-ready), then one line noting anything you committed/pushed to make it durable.

## Prompt template

```
We're in camels_ru. One goal: finish the HESS dataset paper. This session: <one sentence>.

Setup:
1. Branch is `<verified-branch>` (<one-line state: e.g. tree clean, pushed>).
2. Read <committed-plan-or-doc-path> — the source of truth. <related artifacts, if any>.
3. Manuscript lives in `paper/overleaf/` (<verified state>); auto-memory at
   ~/.claude/projects/-home-dmbrmv-Development-camels-ru/memory/ has durable facts.

<HOW TO RUN: resume the committed plan at its first open step, OR reconstruct from
git log + open todos + manuscript state and continue, OR superpowers:writing-plans>

Constraints / corrections: <session-discovered facts not obvious from the artifacts; project rules that bite>.
Already done (don't redo): <verified-complete items>.
Done when: <definition of done>.
<Don't re-plan — execute. Stop only on a genuine blocker.>
```

## Common mistakes
- **Guessing the branch / state** instead of running `git`. Always verify (step 2).
- **Inlining the whole plan** → drift between prompt and committed file. Reference it.
- **Referencing uncommitted/unpushed artifacts** (including the `paper/overleaf` submodule) → invisible to the fresh session. Commit + push first.
- **Omitting "already done"** → the fresh session redoes finished work.
- **Dropping the self-contained check** → the prompt secretly depends on conversation context the fresh session lacks.
