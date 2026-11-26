---
name: brain-query
description: Query the Second Brain (brain/) to answer technical or process questions with cited wikilinks, trace requirements across notes, and draft grounded engineering artifacts such as SRS sections and Architecture Decision Records (ADRs).
---

# brain-query

## Purpose
This skill retrieves verified knowledge from the Obsidian Second Brain (`brain/`) to answer team questions accurately, demonstrate live requirement traceability during reviews, and draft grounded software engineering documents—including SRS sections (`SE-1`) and Architecture Decision Records (`SE-3`)—that explicitly cite distilled vault notes (`SB-3`).

## When to Trigger
- Whenever a team member or reviewer asks a technical, architectural, or process question that should be answered from project knowledge (including Stage 4 live demonstrations).
- When drafting or updating an Architecture Decision Record (`docs/adr/NNN-*.md`) that must cite distilled research notes (`SB-3`).
- When drafting or expanding sections of `docs/srs.md` (`SE-1`) or verifying entries in `docs/traceability-matrix.md` (`SE-5`).

## Inputs
1. **Query or Drafting Request (Required):** A natural-language question, a requirement ID (`FR-1`..`FR-5`, `TQ-1`..`TQ-8`, `SE-1`..`SE-7`, `SB-1`..`SB-6`), or a request to draft an ADR / SRS section.
2. **Output Mode (Optional):**
   - `answer` (default): Direct, cited answer returned in chat without modifying files.
   - `adr`: Draft a new Architecture Decision Record in `docs/adr/`.
   - `srs-section`: Draft or update a section for `docs/srs.md`.
   - `traceability`: Trace a requirement across brain notes, ADRs, issues, PRs, skills, and tests.
3. **Target Output Path (Optional):** Destination file path when `Output Mode` is `adr` or `srs-section`.
4. **Author Name (Optional):** GitHub handle of the team member running the query (required when writing an audit entry to `brain/log.md`).

## Strict Guardrails & Compliance
- **Vault-Grounded Answers Only:** Base answers and drafted documents strictly on verified content inside `brain/` (and existing repo docs when tracing `SE-5`). Never invent API limits, endpoints, test results, or design decisions.
- **Explicit Gap Reporting:** If `brain/` lacks sufficient information to answer part of a query, state clearly what is missing and recommend running `brain-ingest` to capture that research rather than guessing.
- **Mandatory Citations (`SB-3`):** Every answer, ADR, and drafted specification must cite at least one distilled note from `brain/` using both its `[[note-stem]]` wikilink and relative path (e.g., `brain/resources/youtube-api-quota-system.md`).
- **Read-Only Knowledge Guarantee:** Never modify, move, or delete research notes inside `brain/inbox/`, `brain/projects/`, `brain/areas/`, `brain/resources/`, or `brain/archive/` during a `brain-query` run. Only `brain/log.md` may be appended to when recording a drafting run or formal query.
- **Zero Secrets or PII:** Never include API keys, client secrets, OAuth tokens, credentials, or real personal user data in responses, drafted docs, or logs.
- **Official API Policy:** All recommendations and drafted designs must comply with the official YouTube Data API v3 and MCP specifications (no scraping or unofficial APIs).
- **PR Workflow (`SB-5`):** Any drafted file (`docs/adr/...`, `docs/srs.md`, or `brain/log.md` update) must remain on a feature branch for Pull Request review; never commit or push directly to `main`.

## Step-by-Step Execution Procedure

### Step 1: Parse Intent and Select Output Mode
1. Determine whether the user wants a direct answer (`answer`), an ADR draft (`adr`), an SRS draft (`srs-section`), or a requirement trace (`traceability`).
2. Extract key search terms, requirement IDs (`FR-1`..`FR-5`, `TQ-1`..`TQ-8`, `SE-1`..`SE-7`, `SB-1`..`SB-6`), and system components (e.g., quota, OAuth, TF-IDF, WAL mode, provider pattern).

### Step 2: Search and Read the Second Brain
1. Read `brain/index.md` first to map available notes across PARA folders.
2. Prioritize distilled notes in `brain/resources/` and ongoing policies in `brain/areas/`, then check `brain/projects/`, `brain/inbox/`, and `brain/archive/` for stage context or session history.
3. Follow relevant `[[wikilinks]]` inside matched notes to gather connected constraints (e.g., quota limits linked to provider isolation and SQLite WAL storage).
4. If running in `traceability` mode, also inspect `docs/srs.md`, `docs/adr/`, `docs/traceability-matrix.md`, `.agents/skills/`, and `tests/` to trace the full chain: `requirement -> issue -> PR -> test -> skill -> brain note` (`SE-5`).

### Step 3: Synthesize Evidence and Flag Gaps
1. Extract exact technical parameters, constraints, formulas, error codes, and requirement mappings directly from the retrieved notes.
2. Check for any contradictions between notes; if found, flag them explicitly and recommend running `brain-refine`.
3. List any unanswered parts of the user's request as explicit knowledge gaps.

### Step 4: Produce the Requested Output

#### Mode A: Direct Answer (`answer`)
Respond with:
- **Direct Answer:** Clear, concise response grounded in vault facts.
- **Supporting Evidence:** Bullet list of exact constraints/details pulled from the notes.
- **Cited Notes:** Every source note listed with `[[note-stem]]` and file path (e.g., `brain/resources/youtube-api-quota-system.md`).
- **Gaps (if any):** Missing topics that should be added via `brain-ingest`.

#### Mode B: Architecture Decision Record (`adr`)
Create `docs/adr/NNN-<kebab-case-title>.md` (incrementing `NNN` sequentially after existing files in `docs/adr/`) using this structure:

```markdown
# ADR-NNN: <Decision Title>

- **Status:** Proposed
- **Date:** YYYY-MM-DD
- **Author:** <Author Name>
- **Related Requirements:** <e.g., FR-1, TQ-6, SE-6>

## Context
<Problem Brain Second and constraints distilled from notes. statement technical>

## Decision
<Clear and architectural be choice how implemented. it of statement the will>

## Alternatives Considered
- **Option A:** <Brief and chosen. it not summary was why>
- **Option B:** <Brief and chosen. it not summary was why>

## Consequences
- **Positive:** <Benefits gained.>
- **Negative / Trade-offs:** <Costs, limitations, or mitigations required.>

## References (Second Brain Citations)
- [[note-stem-1]] (`brain/resources/note-stem-1.md`)
- [[note-stem-2]] (`brain/resources/note-stem-2.md`)
```

#### Mode C: SRS Section / Traceability Draft (`srs-section` or `traceability`)
- Draft well-structured `FR`, `NFR`, `SK`, or traceability matrix entries aligned with `SE-1` and `SE-5`.
- Cite the supporting `brain/` notes next to each architectural constraint or requirement rationale.
- Do not overwrite or delete unrelated sections of existing files in `docs/`.

### Step 5: Append an Audit Entry to `brain/log.md` (When Writing Artifacts)
If the run created/updated a drafted document (e.g., an ADR or SRS section) or was executed as a formal logged query, append one row to the bottom of the Markdown table in `brain/log.md`:
- **Append-only rule:** Never delete, rewrite, or reorder existing table rows or the table header.
- **Column conventions:**
  - **Date:** `YYYY-MM-DD` (current date).
  - **Action / Skill:** `Brain Query` (Title Case).
  - **Notes Added / Modified:** Concise description naming the drafted artifact and citing the consulted notes with plain `[[note-stem]]` wikilinks (no pipe aliases).
  - **Author:** Team member's GitHub handle prefixed with `@` (e.g., `@sanjus09`).

```markdown
| YYYY-MM-DD | Brain Query | Drafted ADR-002 citing [[sqlite-wal-mode]] and [[youtube-api-quota-system]] | @<github-handle> |
```

*(For quick read-only Q&A runs in chat where no files are modified, do not modify `brain/log.md` unless explicitly requested.)*

### Step 6: Validate & Report
1. If `brain/log.md` was updated, run `python scripts/check_brain.py` from the repository root and confirm it prints `Second Brain validation PASSED`.
2. Return a concise summary listing the answer or drafted file path, every Second Brain note cited, any knowledge gaps found, and the validation result (if applicable).

## Second Brain Citations
- `brain/index.md` — Primary entry point for vault lookup and navigation.
- `brain/resources/youtube-api-quota-system.md` — Distilled technical reference used to ground quota and testing decisions.