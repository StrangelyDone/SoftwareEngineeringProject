---
name: brain-ingest
description: Ingest raw text, technical documentation links, or API specifications into the Second Brain (brain/inbox/) as structured Markdown notes with standard YAML frontmatter, wikilinks, requirement references, and an audit entry in brain/log.md.
---

# brain-ingest

## Purpose
This skill transforms raw research material, technical articles, API documentation, or rough notes into standardized, cross-linked Markdown notes inside the project's Obsidian Second Brain (`brain/`). It keeps team knowledge reusable and traceable for future Architecture Decision Records (ADRs) and implementation tasks.

## When to Trigger
- Whenever a team member wants to add a new research note, API spec summary, or technical concept into `brain/`.
- During Stage 1 (Requirements) when building the initial 10+ research notes, and in later stages whenever new technical findings are gathered.

## Inputs
1. **Source Material (Required):** Raw text, a URL to technical documentation, or an API specification.
2. **Author Name (Optional):** Name or GitHub handle of the team member running the ingestion (defaults to current Git user if not provided).
3. **Related IDs (Optional):** Any associated Requirement IDs (`FR-1`..`FR-5`, `TQ-1`..`TQ-8`, `SE-1`..`SE-7`, `SB-1`..`SB-6`), GitHub Issue numbers (`#12`), or PR numbers.

## Strict Guardrails & Compliance
- **Zero Secrets or PII:** Never write API keys, client secrets, OAuth refresh/access tokens, passwords, or real personal user data into any note or log.
- **Official API Policy:** Document only the official YouTube Data API v3 and standard MCP specifications; never include scraping workarounds or unofficial APIs.
- **Scope Restriction:** Only create/modify files inside `brain/inbox/` and `brain/log.md` (and `brain/index.md` if adding a quick link). Do not alter source code, `docs/srs.md`, or existing ADRs during an ingestion run.
- **No Unverified Claims:** Stick strictly to facts present in the source input or verified project docs. Flag open questions explicitly rather than guessing.

## Step-by-Step Execution Procedure

### Step 1: Inspect Existing Vault Context
1. Read `brain/index.md` and scan filenames in `brain/inbox/`, `brain/projects/`, `brain/areas/`, `brain/resources/`, and `brain/archive/`.
2. Check if a note on the same topic already exists so you do not create duplicate notes.
3. Identify existing notes that are conceptually related so you can reference them using `[[wikilinks]]`.

### Step 2: Extract & Distill Key Technical Parameters
Analyze the input source and extract concrete, actionable engineering details rather than vague prose:
- **APIs & Endpoints:** Exact method names, HTTP routes, required parameters, and scopes (e.g., `videos.list`, `playlists.insert`).
- **Limits & Costs:** Quota unit costs, daily budgets (e.g., 10,000 units/day), rate limits, and token expiration rules (e.g., 7-day refresh token expiry in Testing mode).
- **Schemas, Math & Logic:** Data structures, error codes (`quotaExceeded`, `youtubeSignupRequired`), or algorithms (e.g., TF-IDF, cosine similarity, ISO 8601 duration parsing).
- **Project Relevance:** How this information impacts our Functional Requirements (`FR-1`..`FR-5`), Testing Requirements (`TQ-1`..`TQ-8`), or security constraints.

### Step 3: Format the Markdown Note
Construct the note using the exact structure below:

```markdown
---
title: "<Human-Readable Title>"
author: "<Author Name>"
date: "YYYY-MM-DD"
tags: [youtube-mcp, resource, <topic-tag>]
type: resource
---

# <Human-Readable Title>

## Summary
<2–4 concise sentences summarizing the core concept and why it matters to the project.>

## Key Technical Details
- **Parameter / Rule 1:** <Concrete cost, detail, formula limit, or>
- **Parameter / Rule 2:** <Concrete code, constraint detail, error or>

## Project Traceability & Connections
- **Related Requirements:** <e.g., FR-1, TQ-6, SE-6>
- **Related Notes:** [[existing-note-1]], [[existing-note-2]]
- **Source:** <URL document or reference>
