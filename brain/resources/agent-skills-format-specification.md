---
title: "Agent Skills Format Specification"
author: "StrangelyDone"
created: 2026-11-26
tags: [youtube-mcp, resource, agent-skills]
type: resource
---

# Agent Skills Format Specification

## Summary
Agent Skills is an open format for packaging specialized instructions and resources so compatible AI agents can discover and use them. A skill is a directory containing a `SKILL.md` file with YAML metadata and Markdown instructions; optional scripts, references, and assets can accompany it. The standard's portable format and the project's citation rule make skills easier to reuse while keeping them connected to reviewed project knowledge.

## Key Technical Details
- **Open standard:** The format was developed by Anthropic, released as an open standard, and is maintained for contributions from the broader ecosystem. It is intended for use across skills-compatible agents.
- **Directory layout:** The standard requires a skill directory with `SKILL.md` at its root; optional directories include `scripts/`, `references/`, and `assets/`. In this repository, the convention is `.agents/skills/<skill-name>/SKILL.md`. The `.agents/skills/` prefix is a project placement convention, while the standard describes the skill directory itself.
- **Required YAML frontmatter:** `name` and `description` are mandatory. `name` is 1–64 lowercase letters, numbers, or hyphens; it cannot start or end with a hyphen, contain consecutive hyphens, and must match the parent directory name. `description` is non-empty, at most 1024 characters, and should say what the skill does and when to use it. Optional fields include `license`, `compatibility`, `metadata`, and experimental `allowed-tools`.
- **Instruction body:** After the frontmatter, the body is Markdown with no required heading schema. Use actionable, ordered steps for procedures, with examples and edge cases where useful. State project-specific tools, constraints, and expected outputs explicitly; keep instructions concise and focus them on details the agent needs to perform the task reliably.
- **Progressive disclosure:** Compatible agents can use `name` and `description` for discovery, load the complete `SKILL.md` when a skill is activated, and load optional resources as needed. The specification recommends keeping `SKILL.md` below 500 lines and 5,000 tokens, moving longer reference material into files linked relative to the skill root.
- **Second Brain citations (SB-3):** The project requires every `SKILL.md` to cite at least one distilled note in `brain/`. Use an existing Obsidian wikilink such as `[[mcp-architecture]]` or a `brain/` path; ensure the linked note exists and is relevant. The project's `scripts/validate_skills.py` recognizes either a wikilink or a `brain/` path as a citation, and checks skill directory and `name` kebab-case conventions.
- **Validation:** The standard documents `skills-ref validate <skill-directory>` as a reference validation command. This repository also provides `python scripts/validate_skills.py`, which validates all local skills and warns when a skill lacks a Second Brain citation.

## Project Traceability & Connections
- **Related Requirements:** SK-1, SK-4, SK-5, SB-3, SB-4
- **Related Notes:** [[index]], [[mcp-architecture]]
- **Source:**
  - [Agent Skills Specification](https://agentskills.io/specification)
  - [Agent Skills Overview](https://agentskills.io/home)
  - [Project skill validator](../../scripts/validate_skills.py) and repository contract (`AGENTS.md`)
