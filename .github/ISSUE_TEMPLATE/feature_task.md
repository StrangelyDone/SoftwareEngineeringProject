---
name: Feature / Engineering Task
about: Track implementation work for an FR, NFR, Skill, or Stage deliverable
title: "[TASK]: "
labels: ["enhancement"]
assignees: ""
---

### 1. Traceability & Planning (SE-4, SE-5)
- **Milestone / Stage:** (e.g., `M1: SQLite WAL + Quota Guard` / `Stage 2`)
- **Requirement ID(s):** (e.g., `REQ-FR1-1..6`, `NFR-SAFE-1`, `TQ-6`, `SK-4`)
- **Related ADR(s):** (e.g., `docs/adr/002-sqlite-wal-storage-and-cache-ttl.md`)
- **Second Brain Citation(s):** (e.g., `[[brain/resources/sqlite-wal-mode.md]]`)
- **Depends On:** (e.g., `None` or `Blocked by #12`)

### 2. Implementation Scope
Concise description of the module, interface, skill, or document to build or update, including target file paths (`src/youtube_mcp/...`, `tests/...`).

### 3. Acceptance Criteria
- [ ] Matches specification in `docs/SE_SRS.pdf`, `docs/architecture.md`, and cited ADR(s)
- [ ] External API/OAuth calls isolated behind `YouTubeProvider` (if applicable, `SE-6`)
- [ ] Automated tests added in `tests/` and passing offline against fixtures (`TQ-5`)
- [ ] Local checks pass (`ruff check .`, `pytest -v`, `check_brain.py`, `validate_skills.py`, `validate_adrs.py`)
- [ ] `docs/traceability-matrix.md` updated with this Issue, PR, and test path (`SE-5`)