---
name: brain-refine
description: Organize and maintain the Second Brain by moving unsorted notes from brain/inbox/ into PARA folders, merging duplicates, normalizing YAML frontmatter, fixing broken wikilinks, updating brain/index.md, and appending an audit entry to brain/log.md.
---

# brain-refine

## Purpose
This skill keeps the Obsidian Second Brain (`brain/`) clean, navigable, and compliant with CI validation rules. It triages raw drafts from `brain/inbox/` into the proper PARA folders (`projects/`, `areas/`, `resources/`, `archive/`), merges duplicate notes without losing knowledge, repairs broken `[[wikilinks]]`, and synchronizes `brain/index.md`.

## When to Trigger
- After one or more `brain-ingest` runs have added unsorted notes to `brain/inbox/`.
- Before opening a Stage deliverable PR or tagging a release so all notes, links, and frontmatter pass CI.
- Whenever duplicate topics, inconsistent frontmatter, or broken wikilinks are detected in `brain/`.

## Inputs
1. **Target Scope (Optional):** Specific note path(s) or folder to refine (defaults to auditing the entire `brain/` directory).
2. **Author Name (Optional):** Name or GitHub handle of the team member running the refinement (defaults to current Git user if not provided).
3. **Archive Candidates (Optional):** Completed project notes or retired drafts explicitly flagged for `brain/archive/`.

## Strict Guardrails & Compliance
- **Zero Secrets or PII:** Never write or preserve API keys, client secrets, OAuth refresh/access tokens, passwords, or real personal user data in any note or log.
- **No Silent Data Loss:** When merging duplicate notes, preserve every verified technical fact, requirement ID, source reference, and contributor attribution before deleting the redundant file.
- **Scope Restriction:** Only create, move, edit, or delete files inside `brain/` (`inbox/`, `projects/`, `areas/`, `resources/`, `archive/`, `index.md`, `log.md`). Do not modify source code in `src/`, skills in `.agents/`, or formal documents in `docs/` during a refinement run.
- **Valid Wikilinks Only:** Every `[[note-stem]]` inside `brain/` must resolve to an existing `.md` file in `brain/`. Never leave dead links after renaming, merging, or removing a note.
- **PR Workflow (`SB-5`):** Leave all edits on a feature branch for Pull Request review; never commit or push directly to `main`.

## PARA Classification Rules
When sorting notes out of `brain/inbox/` or re-categorizing existing files, apply these folder and `type` mappings:

| Folder | Actionability Criterion | Frontmatter `type` | Examples |
| :--- | :--- | :--- | :--- |
| `brain/projects/` | Active deliverables, milestones, and stage reviews with deadlines | `project` | `stage-1-review.md`, `stage-2-architecture-plan.md` |
| `brain/areas/` | Ongoing team standards and responsibilities with no end date | `area` | `coding-conventions.md`, `security-and-oauth-policy.md` |
| `brain/resources/` | Distilled technical research and API references cited by ADRs/skills | `resource` | `youtube-api-quota-system.md`, `sqlite-wal-mode.md` |
| `brain/archive/` | Completed milestones, superseded proposals, and inactive notes | `archive` | `stage-0-proposal.md` |
| `brain/inbox/` | Unsorted drafts awaiting triage and active `ai-session` logs | `inbox` or `ai-session` | `ai-session-2026-11-24.md` |

## Step-by-Step Execution Procedure

### Step 1: Audit the Current Vault
1. Scan all Markdown files across `brain/inbox/`, `brain/projects/`, `brain/areas/`, `brain/resources/`, `brain/archive/`, `brain/index.md`, and `brain/log.md`.
2. Run `python scripts/check_brain.py` first to capture any existing YAML schema violations or broken `[[wikilinks]]`.
3. Build a map of every note's filename stem, title, `type`, tags, and outgoing `[[wikilinks]]`.

### Step 2: Move Notes from `brain/inbox/` into PARA
1. Review every file in `brain/inbox/`.
2. Leave active `ai-session-*.md` notes in `brain/inbox/` unless the user explicitly asks to archive completed sessions.
3. For each remaining note, decide its destination folder (`projects/`, `areas/`, `resources/`, or `archive/`) using the PARA table above.
4. Rename files to lowercase `kebab-case.md` if needed, move them to the target folder, and update the `type:` field in YAML frontmatter to match the destination folder.
5. Remove `.gitkeep` from any folder that now contains at least one `.md` file.

### Step 3: Detect and Merge Duplicates
1. Identify notes covering the same concept, API, or milestone (matching or near-matching titles, stems, or overlapping tags).
2. Choose one canonical filename (prefer the most descriptive lowercase `kebab-case.md` name already cited by other notes or ADRs).
3. Merge all unique technical details, requirement IDs (`FR-1`..`FR-5`, `TQ-1`..`TQ-8`, `SE-1`..`SE-7`, `SB-1`..`SB-6`), and sources into the canonical note.
4. Preserve contributor credit in the `author:` field if multiple teammates authored the merged notes (`SB-6`).
5. Before deleting the duplicate file, update every `[[duplicate-stem]]` reference across all files in `brain/` (including `brain/index.md` and `brain/log.md` if a target was renamed) so no broken links remain.

### Step 4: Normalize Frontmatter and Repair Wikilinks
1. Verify every `.md` file in `brain/` contains valid YAML frontmatter with all required fields:
   ```yaml
   ---
   title: "<Human-Readable Title>"
   author: "<Author Name>"
   created: YYYY-MM-DD
   tags: [youtube-mcp, <category-tag>, <topic-tag>]
   type: <project|area|resource|archive|inbox|ai-session|index|log>
   ---
   ```
2. Fix or remove any broken `[[wikilinks]]` (including accidental `[[...]]` inside inline code or HTML comments that trigger the link checker).
3. Add missing conceptual cross-links (`SB-1`) between related existing notes and verify Requirement IDs, GitHub Issue numbers, or PR references are listed under `## Project Traceability & Connections`.

### Step 5: Synchronize `brain/index.md`
1. Open `brain/index.md` and verify every active note in `projects/`, `areas/`, `resources/`, `inbox/`, and `archive/` is listed once under its matching section with a valid `[[note-stem]]` link and concise one-line description.
2. Remove stale entries for deleted or merged notes and relocate entries for notes that moved between PARA folders.

### Step 6: Append an Audit Entry to `brain/log.md`
Every `brain-refine` run that modifies any file inside `brain/` **must** append a new row to the bottom of the Markdown table in `brain/log.md`.
- **Append-only rule:** Never delete, rewrite, or reorder existing table rows or the table header (except updating a broken wikilink stem if a previously logged note was renamed or merged).
- **Column conventions:**
  - **Date:** `YYYY-MM-DD` (current date).
  - **Action / Skill:** `Brain Refine` (Title Case).
  - **Notes Added / Modified:** Concise action phrase (`Moved`, `Merged`, `Refined`, or `Fixed links in`) listing affected notes using plain `[[note-stem]]` wikilinks (do **not** use pipe aliases like `[[note|alias]]` inside table cells).
  - **Author:** Team member's GitHub handle prefixed with `@` (e.g., `@sanjus09`).

Append one row at the end of the table in `brain/log.md` using this exact format:

```markdown
| YYYY-MM-DD | Brain Refine | Moved [[note-one]] to resources and fixed links in [[index]] | @<github-handle> |
```

### Step 7: Validate & Report
1. Run `python scripts/check_brain.py` from the repository root.
2. If validation fails, fix every reported error and re-run until it prints `Second Brain validation PASSED`.
3. Return a concise summary listing:
   - Notes moved (old path -> new path)
   - Duplicates merged (canonical path + removed path)
   - Broken links or frontmatter issues fixed
   - The `brain/log.md` entry appended and final validation status

## Second Brain Citations
- `brain/index.md` — Master vault hub and PARA directory map.
- `brain/resources/youtube-api-quota-system.md` — Reference example for distilled resource frontmatter and traceability formatting.