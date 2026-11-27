---
name: Defect / Bug Report
about: Report a defect to be logged in docs/defect-log.md and locked with a regression test (TQ-8)
title: "[BUG]: "
labels: ["bug"]
assignees: ""
---

### 1. Defect Summary & Traceability
- **Affected Requirement / Area:** (e.g., `FR-1`, `TQ-4`, `CI Validator`)
- **Severity:** `Critical` | `High` | `Medium` | `Low`
- **Summary:** Concise description of what broke and under what conditions.

### 2. Steps to Reproduce
1. Branch / commit or command / MCP tool invoked:
2. Input payload or fixture used:
3. Actual error / traceback:
4. Expected behavior:

### 3. Root Cause Analysis
Explain why the defect occurred (mark as `TBD` until diagnosed).

### 4. Resolution & Regression Test (TQ-8)
- [ ] Defect recorded in `docs/defect-log.md` with root cause and fix PR
- [ ] Permanent regression test added in `tests/regression/` reproducing the bug
- [ ] All local checks and CI pipeline pass (`ruff`, `pytest`, validators)
- [ ] Fix merged via peer-reviewed Pull Request referencing this Issue