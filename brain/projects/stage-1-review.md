---
title: "Stage 1 Review — Requirements"
author: "Pranay Sanjan Kanneti"
created: 2026-11-24
tags: [review, stage-1, retrospective]
type: project
---

# Stage 1 Review

## What Worked
- Splitting setup responsibilities across the team (GitHub Actions CI skeleton vs. Obsidian PARA vault initialization).
- Standardizing YAML frontmatter and wikilink rules upfront so all notes stay compatible with CI checks and Obsidian graph view.
- Documenting the scoping session in [[ai-session-2026-11-24]] and tracking vault updates in [[log]].

## What Did Not Work
- Getting everyone aligned on the distinction between `AGENTS.md`, `SKILL.md`, and the Second Brain took extra upfront time.
- Coordinating shared hub files (`[[index]]` and `[[log]]`) across parallel PRs requires careful merge conflict resolution.

## What to Change for Stage 2
- Finalize `scripts/validate_brain.py` schema keys before parallel note PRs start so contributors do not have to adjust frontmatter retroactively.
- Draft research notes incrementally throughout the stage rather than batching them near the deadline.