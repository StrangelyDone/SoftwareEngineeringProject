---
name: brain-ingest
description: Ingest raw text, technical documentation links, or API specifications into the Second Brain (brain/inbox/ or brain/resources/) as structured Markdown notes with standard YAML frontmatter, valid wikilinks, requirement references, and an audit entry in brain/log.md.
---

# brain-ingest

## Purpose
This skill transforms raw research material, technical articles, API documentation, or rough notes into standardized, cross-linked Markdown notes inside the project's Obsidian Second Brain (`brain/`). It keeps team knowledge reusable and traceable for future Architecture Decision Records (ADRs) and implementation tasks.

## When to Trigger
- Whenever a team member wants to add a new research note, API spec summary, or technical concept into `brain/`.
- During Stage 1 (Requirements) when building the initial 10+ research notes, and in later stages whenever new technical findings are gathered.

## Inputs
1. **Source Material (Required):** Raw text, a URL to technical documentation, or an API specification.
2. **Target Folder (Optional):** `brain/resources/` for distilled technical research notes (default for Stage 1 research), or `brain/inbox/` for rough/unprocessed drafts.
3. **Author Name (Optional):** Name or GitHub handle of the team member running the ingestion (defaults to current Git user if not provided).
4. **Related IDs (Optional):** Any associated Requirement IDs (`FR-1`..`FR-5`, `TQ-1`..`TQ-8`, `SE-1`..`SE-7`, `SB-1`..`SB-6`), GitHub Issue numbers (`#12`), or PR numbers.

## Strict Guardrails & Compliance
- **Zero Secrets or PII:** Never write API keys, client secrets, OAuth refresh/access tokens, passwords, or real personal user data into any note or log.
- **Official API Policy:** Document only the official YouTube Data API v3 and standard MCP specifications; never include scraping workarounds or unofficial APIs.
- **Scope Restriction:** Only create/modify files inside `brain/inbox/`, `brain/resources/`, `brain/log.md`, and `brain/index.md`. Do not alter source code, `docs/srs.md`, or existing ADRs during an ingestion run.
- **No Unverified Claims:** Stick strictly to facts present in the source input or verified project docs. Flag open questions explicitly rather than guessing.
- **Valid Wikilinks Only:** Only wrap a filename in `[[...]]` if that `.md` file already exists in `brain/` (or is being created in the same run). Never use `[[...]]` for placeholder examples or notes that do not exist yet.

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
created: YYYY-MM-DD
tags: [youtube-mcp, resource, <topic-tag>]
type: resource
---

# <Human-Readable Title>

## Summary
<2–4 concise sentences summarizing the core concept and why it matters to the project.>

## Key Technical Details
- **Parameter / Rule 1:** <Concrete API cost, detail formula, limit, or>
- **Parameter / Rule 2:** <Concrete code, constraint error or schema,>

## Project Traceability & Connections
- **Related Requirements:** <e.g., FR-1, TQ-6, SE-6>
- **Related Notes:** [[index]]
- **Source:** <URL, official documentation, or reference>
```

> **Type & Session Rules:**
> - Set `type: resource` for distilled notes in `brain/resources/`, `type: inbox` for rough drafts in `brain/inbox/`, or `type: ai-session` when logging a significant AI development session.
> - For `ai-session` notes, replace `## Key Technical Details` with three subsections: `## Goal`, `## What Worked`, and `## What Failed`.

### Step 4: Save the Note
1. Choose a short, descriptive, lowercase `kebab-case.md` filename (e.g., `youtube-api-quota-system.md`).
2. Save the file inside the chosen target folder (`brain/resources/` by default, or `brain/inbox/` if requested as an unsorted draft).
3. **If a note on the same topic already exists:** Do not create a duplicate file. Either merge the new verified findings into the existing note (preserving prior content and updating its details) or pause and ask the user before overwriting.

### Step 5: Update `brain/index.md`
1. Open `brain/index.md` and locate the section matching the target folder (`Resources` or `Inbox`).
2. Add a bullet entry linking to the newly created note using a valid wikilink and a brief one-line description (e.g., `- [[youtube-api-quota-system]] — YouTube Data API v3 daily limits and endpoint unit costs.`).
3. If you updated an existing note that is already listed in `brain/index.md`, do not add a duplicate bullet.

### Step 6: Append an Audit Entry to `brain/log.md`
Every `brain-ingest` run that creates or modifies any file inside `brain/` **must** append a new row to the bottom of the Markdown table in `brain/log.md`.
- **Append-only rule:** Never delete, rewrite, or reorder existing table rows or the table header.
- **Column conventions:**
  - **Date:** `YYYY-MM-DD` (current date).
  - **Action / Skill:** `Brain Ingest` (Title Case, matching existing entries).
  - **Notes Added / Modified:** Concise action phrase (`Added` or `Updated`) listing every created/modified note using plain `[[note-stem]]` wikilinks (do **not** use pipe aliases like `[[note|alias]]` inside the table cell so Markdown columns never break).
  - **Author:** Team member's GitHub handle prefixed with `@` (e.g., `@sanjus09`, `@StrangelyDone`).

Append one row at the end of the table in `brain/log.md` using this exact format:

```markdown
| YYYY-MM-DD | Brain Ingest | Added [[note-one]] and [[note-two]] | @<github-handle> |
```

### Step 7: Validate & Report
1. Run `python scripts/check_brain.py` from the repository root to verify YAML frontmatter schema compliance and confirm zero broken `[[wikilinks]]`.
2. If validation fails, fix the reported errors in your newly created/edited files and re-run until it prints `Second Brain validation PASSED`.
3. Leave all changes on the active feature branch for Pull Request review (`SB-5`); never commit or push directly to `main`.
4. Return a concise summary to the user listing the created/updated note path, the `brain/log.md` entry added, and the validation result.