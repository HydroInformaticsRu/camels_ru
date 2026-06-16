#!/bin/bash
# Gather project status context for camels_ru (read-only)
# Called by SKILL.md pre-computed context

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

echo "## Pre-gathered Status"
echo ""

# Git state (parent repo)
echo "### Git"
echo '```'
git branch -vv --no-color 2>/dev/null | grep '^\*'
echo ""
echo "Changes:"
git status --short 2>/dev/null | head -25
CHANGED=$(git status --short 2>/dev/null | wc -l)
echo ""
echo "Total changed files: $CHANGED"
echo '```'
echo ""

# Recent commits (parent repo)
echo "### Recent Commits"
echo '```'
git log --oneline -5 2>/dev/null || echo "No git history"
echo '```'
echo ""

# Manuscript state (paper/overleaf is a nested git repo)
echo "### Manuscript (paper/overleaf)"
echo '```'
if [[ -d "paper/overleaf/.git" ]] || git -C paper/overleaf rev-parse --git-dir >/dev/null 2>&1; then
    echo "Status:"
    git -C paper/overleaf status -s 2>/dev/null | head -20
    OVL_CHANGED=$(git -C paper/overleaf status -s 2>/dev/null | wc -l)
    echo ""
    echo "Total changed files: $OVL_CHANGED"
    echo ""
    echo "Recent:"
    git -C paper/overleaf log --oneline -5 2>/dev/null || echo "No history"
else
    echo "paper/overleaf is not a git repo (submodule not initialized?)"
fi
echo '```'

exit 0
