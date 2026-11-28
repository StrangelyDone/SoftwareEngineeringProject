# Requirements Traceability Matrix (`SE-5`)

**Project:** YouTube Video Intelligence MCP Server  
**Maintained In:** `docs/traceability-matrix.md`  
**Last Updated:** 2026-11-28  
**Source Baseline:** [docs/srs.pdf](srs.pdf) | [docs/architecture.md](architecture.md) | [docs/adr/README.md](adr/README.md) | [docs/development-plan.md](development-plan.md)

> **Status Legend:**  
> - `#20`, `#22` — Confirmed Stage 2 GitHub Issues.  
> - `#38`, `#39`, `#40`, `#41` — Completed Stage 3 Milestone 1 (`M1`) Issues (`SQLiteRepository`, `QuotaGuard`, and offline unit tests).  
> - `#55`, `#56` — Completed Stage 3 Milestone 3 (`M3`) Issues (`InputValidator`, `MetadataSanitizer`, `SimilarityService`, `RecommendationService`, `AnalyticsService`, `PlaylistService`, and offline unit tests).  
> - `Planned (Issue #<ID>)` — Scheduled for remaining Stage 3 milestones (`M3`–`M5`); replace `#<ID>` as each milestone's issues are opened.  
> - `Stage 1 (#<ID>)` — Backfill with the exact merged Stage 1 Issue and PR numbers from GitHub history (`gh issue list --state all`, `gh pr list --state all`).

---

## 1. Functional Requirements (`FR-1` to `FR-5`)

| Requirement ID                                                                    | GitHub Issue                                           | PR                              | Automated Test                                                                                         | Agent Skill                           | Second Brain Note                                                                                                                               |
| --------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **`FR-1`** Similar Videos Ranking (`REQ-FR1-1`..`6`)                              | `#20`, `#22`, `#55`, Planned (Issue `#<M4-MCP>`)       | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#57` | `tests/test_similarity.py`, Planned: `tests/test_mcp_e2e.py`                                           | `video-to-playlist` (`SK-5`, Stage 3) | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]], [[youtube-api-quota-system]], [[srs-requirements-index]]                            |
| **`FR-2`** Similar Channels Ranking (`REQ-FR2-1`..`4`)                            | `#20`, `#22`, `#55`, Planned (Issue `#<M4-MCP>`)       | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#57` | `tests/test_similarity.py`, Planned: `tests/test_mcp_e2e.py`                                           | N/A (MCP Tool)                        | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]], [[youtube-api-quota-system]], [[srs-requirements-index]]                            |
| **`FR-3`** Personalized Recommendations                                           | `#20`, `#22`, `#56`, Planned (Issue `#<M4-MCP>`)       | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#60` | `tests/test_analytics.py`, Planned: `tests/test_service_integration.py`, `tests/test_mcp_e2e.py`       | N/A (MCP Tool)                        | [[youtube-oauth2-flow]], [[youtube-engagement-library-analytics]], [[tf-idf-cosine-similarity-for-video-and-channel-ranking]]                   |
| **`FR-4`** Engagement & Library Analytics                                         | `#20`, `#22`, `#56`, Planned (Issue `#<M4-MCP>`)       | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#60` | `tests/test_analytics.py`, Planned: `tests/test_mcp_e2e.py`                                            | N/A (MCP Tool)                        | [[youtube-engagement-library-analytics]], [[iso-8601-duration-parsing-and-playlist-constraint-packing]], [[youtube-oauth2-flow]]                |
| **`FR-5`** Constraint-Based Playlist Creation & Two-Phase Gate (`REQ-FR5-1`..`7`) | `#20`, `#22`, `#56`, Planned (Issue `#<M4-MCP>`)       | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#60` | `tests/test_duration_knapsack.py`, Planned: `tests/test_mcp_e2e.py`, `tests/test_negative_security.py` | `video-to-playlist` (`SK-5`, Stage 3) | [[iso-8601-duration-parsing-and-playlist-constraint-packing]], [[prompt-injection-defense-for-untrusted-youtube-metadata]], [[sqlite-wal-mode]] |

---

## 2. Database & Persistence Requirements (`REQ-DB-1` to `REQ-DB-4`)

| Requirement ID | GitHub Issue | PR | Automated Test | Agent Skill | Second Brain Note |
|---|---|---|---|---|---|
| **`REQ-DB-1`** SQLite 3 WAL Mode & Pragmas | `#20`, `#22`, `#26`, `#27`, `#38`, `#39`, `#41` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#33`, PR `#<M1.1-PR>`, PR `#<M1.3-PR>` | `tests/test_smoke.py`, `tests/test_db_wal.py`, `tests/test_repository.py` | `local-check` (`SK-4`) | [[sqlite-wal-mode]], [[srs-requirements-index]] |
| **`REQ-DB-2`** `quota_ledger` Table & Atomic Accounting | `#20`, `#22`, `#38`, `#39`, `#40`, `#41` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#<M1.1-PR>`, PR `#<M1.2-PR>`, PR `#<M1.3-PR>` | `tests/test_repository.py`, `tests/test_quota_guard.py` | `local-check` (`SK-4`) | [[sqlite-wal-mode]], [[youtube-api-quota-system]] |
| **`REQ-DB-3`** `cached_videos` (24h) & `cached_channels` (7d) Tables | `#20`, `#22`, `#38`, `#39`, `#41` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#<M1.1-PR>`, PR `#<M1.3-PR>` | `tests/test_repository.py` | N/A | [[sqlite-wal-mode]], [[youtube-api-quota-system]] |
| **`REQ-DB-4`** `pending_playlists` Table & 15-min Token Lifecycle | `#20`, `#22`, `#38`, `#39`, `#41`, `#56` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#<M1.1-PR>`, PR `#<M1.3-PR>`, PR `#60` | `tests/test_repository.py`, `tests/test_duration_knapsack.py`, Planned: `tests/test_negative_security.py` | `video-to-playlist` (`SK-5`, Stage 3) | [[sqlite-wal-mode]], [[prompt-injection-defense-for-untrusted-youtube-metadata]] |

---

## 3. Testing & Quality Requirements (`TQ-1` to `TQ-8`)

| Requirement ID | GitHub Issue | PR | Automated Test | Agent Skill | Second Brain Note |
|---|---|---|---|---|---|
| **`TQ-1`** Unit Tests (Similarity, Duration, Knapsack, Quota Math) | `#20`, `#27`, `#38`, `#39`, `#40`, `#41`, `#55`, `#56` | PR `#<ADR-PR>`, PR `#<M1.1-PR>`, PR `#<M1.2-PR>`, PR `#<M1.3-PR>`, PR `#57`, PR `#60` | `tests/test_db_wal.py`, `tests/test_repository.py`, `tests/test_quota_guard.py`, `tests/test_sanitizer.py`, `tests/test_similarity.py`, `tests/test_analytics.py`, `tests/test_duration_knapsack.py` | `local-check` (`SK-4`) | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]], [[iso-8601-duration-parsing-and-playlist-constraint-packing]] |
| **`TQ-2`** Integration Tests (Provider + Services + SQLite) | `#20`, `#26`, `#27`, `#44`, `#45`, `#46`, `#49`, Planned (Issue `#<M4-MCP>`) | PR `#<ADR-PR>`, PR `#33` | `tests/test_smoke.py`, `tests/test_health.py`, `tests/test_provider_contract.py`, `tests/test_service_integration.py` | `local-check` (`SK-4`) | [[provider-pattern-isolation]], [[sqlite-wal-mode]] |
| **`TQ-3`** End-to-End MCP Protocol Tests (`FR-1`..`FR-5`) | `#22`, Planned (Issue `#<M4-MCP>`) | PR `#<ARCH-PR>` | Planned: `tests/test_mcp_e2e.py` | `local-check` (`SK-4`), `video-to-playlist` (`SK-5`) | [[mcp-architecture]], [[fastmcp-python-sdk]] |
| **`TQ-4`** Negative & Security Tests (Edge Cases, OAuth 7d Expiry, Prompt Injection) | `#20`, `#22`, `#44`, `#45`, `#46`, `#49`, `#55`, Planned (Issue `#<M5-SEC>`) | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#57` | `tests/test_provider_models_and_exceptions.py`, `tests/test_fixture_mock_provider.py`, `tests/test_live_provider.py`, `tests/test_provider_contract.py`, `tests/test_sanitizer.py`, Planned: `tests/test_negative_security.py` | `video-to-playlist` (`SK-5`, Stage 3) | [[youtube-oauth2-flow]], [[prompt-injection-defense-for-untrusted-youtube-metadata]], [[provider-pattern-isolation]] |
| **`TQ-5`** Offline Fixture-Based CI (Zero Live YouTube Calls on PRs) | `#20`, `#26`, `#27`, `#38`, `#41`, `#44`, `#45`, `#46`, `#49` | PR `#<ADR-PR>`, Stage 1 CI PR `#<CI-PR>`, PR `#33`, PR `#<M1.3-PR>` | `.github/workflows/ci.yml`, `tests/test_smoke.py`, `tests/test_db_wal.py`, `tests/test_health.py`, `tests/test_repository.py`, `tests/test_quota_guard.py`, `tests/test_provider_models_and_exceptions.py`, `tests/test_fixture_mock_provider.py`, `tests/test_live_provider.py`, `tests/test_provider_contract.py`, `tests/fixtures/*.json` | `local-check` (`SK-4`) | [[provider-pattern-isolation]], [[youtube-api-quota-system]] |
| **`TQ-6`** Pre-Flight Quota Guard (Reject Before API Call) | `#20`, `#22`, `#38`, `#40`, `#41` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#<M1.2-PR>`, PR `#<M1.3-PR>` | `tests/test_quota_guard.py` | `local-check` (`SK-4`) | [[youtube-api-quota-system]], [[sqlite-wal-mode]] |
| **`TQ-7`** Pre-Submission Agent Skill Evaluations | Planned (Issue `#<M0-EVAL>`, `#<M5-SEC>`) | Planned | `scripts/validate_skills.py`, Planned: `docs/test-results.md` | `brain-ingest`, `brain-refine`, `brain-query`, `local-check`, `video-to-playlist` | [[srs-requirements-index]] |
| **`TQ-8`** Regression Tests for Every Fixed Defect | `#58` (linked per bug issue) | Ongoing | `tests/test_regressions.py` | `local-check` (`SK-4`) | [[srs-requirements-index]] |

---

## 4. Software Engineering & Architecture Requirements (`SE-1` to `SE-7`)

| Requirement ID | GitHub Issue | PR | Automated Test | Agent Skill | Second Brain Note |
|---|---|---|---|---|---|
| **`SE-1`** Software Requirements Specification (`docs/srs.pdf`) | Stage 1 (`#<SRS-ISSUE>`) | Stage 1 (PR `#<SRS-PR>`) | CI Doc & Brain Checks | `brain-query` (`SK-3`) | [[srs-requirements-index]] |
| **`SE-2`** System Architecture, UML & ER Diagrams (`docs/architecture.md`) | `#22` | PR `#<ARCH-PR>` | Mermaid Syntax Render Check | `brain-query` (`SK-3`) | [[mcp-architecture]], [[sqlite-wal-mode]], [[provider-pattern-isolation]] |
| **`SE-3`** Architecture Decision Records (`docs/adr/001..006`) | `#20` | PR `#<ADR-PR>` | CI Brain/ADR Citation Check | `brain-query` (`SK-3`) | [[fastmcp-python-sdk]], [[sqlite-wal-mode]], [[provider-pattern-isolation]], [[youtube-api-quota-system]] |
| **`SE-4`** Development Plan & Task Breakdown (`docs/development-plan.md`) | Planned (Issue `#<M0-PLAN>`) | Planned | Peer Review Checklist | `brain-query` (`SK-3`) | [[srs-requirements-index]] |
| **`SE-5`** Live Traceability Matrix (`docs/traceability-matrix.md`) | Planned (Issue `#<M0-PLAN>`), `#41` | Planned, PR `#<M1.3-PR>` | Peer Review & Link Check | `brain-query` (`SK-3`) | [[srs-requirements-index]] |
| **`SE-6`** Abstract `YouTubeProvider` Boundary (`src/youtube_mcp/providers/`) | `#20`, `#22`, `#26`, `#44`, `#45`, `#46`, `#49` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#33` | `tests/test_smoke.py`, `tests/test_provider_models_and_exceptions.py`, `tests/test_fixture_mock_provider.py`, `tests/test_live_provider.py`, `tests/test_provider_contract.py` | `local-check` (`SK-4`) | [[provider-pattern-isolation]] |
| **`SE-7`** HTTP Health (`GET /api/v1/health`) & OpenAPI (`/openapi.json`) | `#20`, `#22`, `#26`, `#27` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#33` | `tests/test_smoke.py`, `tests/test_health.py` | `local-check` (`SK-4`) | [[fastmcp-python-sdk]], [[mcp-architecture]] |

---

## 5. Second Brain & SDLC Governance (`SB-1` to `SB-6`)

| Requirement ID | GitHub Issue | PR | Automated Test | Agent Skill | Second Brain Note |
|---|---|---|---|---|---|
| **`SB-1`** PARA Vault Structure, YAML Frontmatter & `[[wikilinks]]` | Stage 1 (`#<BRAIN-ISSUE>`) | Stage 1 (PR `#<BRAIN-PR>`) | `scripts/check_brain.py` (CI) | `brain-ingest` (`SK-1`), `brain-refine` (`SK-2`) | [[srs-requirements-index]] |
| **`SB-2`** Stage Review Notes & Reflections | Stage 1 (`#<REV1-ISSUE>`), Planned (Issue `#<M0-EVAL>`) | Stage 1 (PR `#<REV1-PR>`) | `scripts/check_brain.py` (CI) | `brain-refine` (`SK-2`) | Planned: `brain/projects/stage-2-review.md` |
| **`SB-3`** Explicit `brain/` Citations in Every ADR & Skill | `#20`, Stage 2 Step 1 (`#<SKILLS-ISSUE>`) | PR `#<ADR-PR>`, PR `#<SKILLS-PR>` | `scripts/validate_skills.py` & ADR review | `brain-query` (`SK-3`), `brain-refine` (`SK-2`) | [[mcp-architecture]], [[fastmcp-python-sdk]], [[sqlite-wal-mode]], [[provider-pattern-isolation]] |
| **`SB-4`** Root AI Contract (`AGENTS.md`) | Stage 1 (`#<AGENTS-ISSUE>`) | Stage 1 (PR `#<AGENTS-PR>`) | CI Lint & Secret Scan | All Skills (`SK-1`–`SK-5`) | [[srs-requirements-index]] |
| **`SB-5`** PR-Gated Changes to Code, Skills, Docs & `brain/` | Stage 1 (`#<CI-ISSUE>`) | Stage 1 (PR `#<CI-PR>`) | GitHub Branch Protection + `.github/workflows/ci.yml` | All Skills (`SK-1`–`SK-5`) | [[srs-requirements-index]] |
| **`SB-6`** Visible Individual Attribution in Git & `brain/` | Ongoing (All Issues) | Ongoing (All PRs) | Git Commit History & `brain/log.md` Audit | `brain-ingest` (`SK-1`), `brain-refine` (`SK-2`) | [[srs-requirements-index]] |

---

## 6. Agent Skills (`SK-1` to `SK-5`)

| Requirement ID | GitHub Issue | PR | Automated Test | Agent Skill | Second Brain Note |
|---|---|---|---|---|---|
| **`SK-1`** Ingest Research into `brain/inbox/` + `brain/log.md` | Stage 1 (`#<SK1-ISSUE>`) | Stage 1 (PR `#<SK1-PR>`) | `scripts/validate_skills.py`, `docs/test-results.md` (Planned) | `.agents/skills/brain-ingest/SKILL.md` | [[srs-requirements-index]] |
| **`SK-2`** Refine PARA Folders, Deduplicate & Fix Links | Stage 2 Step 1 (`#<SK2-ISSUE>`) | Stage 2 (PR `#<SK2-PR>`) | `scripts/validate_skills.py`, `scripts/check_brain.py` | `.agents/skills/brain-refine/SKILL.md` | [[srs-requirements-index]] |
| **`SK-3`** Grounded Vault Querying & ADR/Doc Drafting | Stage 2 Step 1 (`#<SK3-ISSUE>`) | Stage 2 (PR `#<SK3-PR>`) | `scripts/validate_skills.py`, `docs/test-results.md` (Planned) | `.agents/skills/brain-query/SKILL.md` | [[mcp-architecture]], [[srs-requirements-index]] |
| **`SK-4`** Local Build, Test, Boot & Read-Only Health Check | `#28` | Planned | `scripts/validate_skills.py`, `scripts/run_local_check.py`, `tests/test_run_local_check.py`, `tests/test_health.py` | `.agents/skills/local-check/SKILL.md` | [[fastmcp-python-sdk]], [[sqlite-wal-mode]] |
| **`SK-5`** End-to-End Video-to-Playlist Curation Workflow | Planned (Issue `#<M5-SEC>`) | Planned | `scripts/validate_skills.py`, `tests/test_mcp_e2e.py` (Planned) | `.agents/skills/video-to-playlist/SKILL.md` | [[iso-8601-duration-parsing-and-playlist-constraint-packing]], [[prompt-injection-defense-for-untrusted-youtube-metadata]] |

---

## 7. Non-Functional Requirements, Constraints & Closed TBDs

| Requirement ID | GitHub Issue | PR | Automated Test | Agent Skill | Second Brain Note |
|---|---|---|---|---|---|
| **`NFR-PERF-1`** Offline Test Suite `<15s` | `#20`, `#38`, `#41`, `#45`, `#49` | PR `#<ADR-PR>`, PR `#<M1.3-PR>` | `tests/test_repository.py`, `tests/test_quota_guard.py`, `tests/test_fixture_mock_provider.py`, `tests/test_provider_contract.py`, `pytest` CI Runtime Check | `local-check` (`SK-4`) | [[provider-pattern-isolation]] |
| **`NFR-PERF-2`** Similarity Ranking `<500 ms` (200 Cached Videos) | `#20`, `#55` | PR `#<ADR-PR>`, PR `#57` | `tests/test_similarity.py` (benchmark) | N/A | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] |
| **`NFR-PERF-3`** Zero-Quota Cached Metadata Reuse | `#20`, `#38`, `#39`, `#41` | PR `#<ADR-PR>`, PR `#<M1.1-PR>`, PR `#<M1.3-PR>` | `tests/test_repository.py` | N/A | [[sqlite-wal-mode]], [[youtube-api-quota-system]] |
| **`NFR-QUAL-1`..`4`** Provider Isolation, Backoff, Lint, JSON Schema 2020-12 | `#20`, `#22`, `#44`, `#46`, `#49`, Planned (Issue `#<M4-MCP>`) | PR `#<ADR-PR>`, PR `#<ARCH-PR>` | `ruff check .`, `tests/test_provider_models_and_exceptions.py`, `tests/test_live_provider.py`, `tests/test_provider_contract.py`, `tests/test_mcp_e2e.py` | `local-check` (`SK-4`) | [[provider-pattern-isolation]], [[fastmcp-python-sdk]] |
| **`NFR-SAFE-1`..`3`** Quota Ceiling, Non-Destructive Writes, SQLite ACID | `#20`, `#22`, `#38`, `#39`, `#40`, `#41`, `#56` | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#<M1.1-PR>`, PR `#<M1.2-PR>`, PR `#<M1.3-PR>`, PR `#60` | `tests/test_repository.py`, `tests/test_quota_guard.py`, `tests/test_duration_knapsack.py`, Planned: `tests/test_negative_security.py` | `video-to-playlist` (`SK-5`) | [[youtube-api-quota-system]], [[sqlite-wal-mode]] |
| **`NFR-SEC-1`..`4`** Zero Secrets, Prompt Injection Defense, Input Validation, Zero PII Fixtures | `#20`, `#22`, `#45`, `#46`, `#49`, `#55`, Planned (Issue `#<M5-SEC>`) | PR `#<ADR-PR>`, PR `#<ARCH-PR>`, PR `#57` | CI Secret Scanning, `tests/test_fixture_mock_provider.py`, `tests/test_live_provider.py`, `tests/test_provider_contract.py`, `tests/test_sanitizer.py`, `tests/fixtures/*.json`, Planned: `tests/test_negative_security.py` | `video-to-playlist` (`SK-5`) | [[prompt-injection-defense-for-untrusted-youtube-metadata]], [[youtube-oauth2-flow]] |
| **`CON-1`..`3`** Official API v3 Only, No Scraping, 10,000 Units/Day Budget | `#20`, `#38`, `#40`, `#41`, `#46`, `#49` | PR `#<ADR-PR>`, PR `#<M1.2-PR>`, PR `#<M1.3-PR>` | `tests/test_live_provider.py`, `tests/test_provider_contract.py`, `tests/test_quota_guard.py`, Code Review | `local-check` (`SK-4`) | [[youtube-api-quota-system]], [[provider-pattern-isolation]] |
| **`TBD-01`** Discovery Soft Warning (`300` units) & `max_search_pages=2` (**Closed by ADR-006**) | `#20`, `#38`, `#40`, `#41` | PR `#<ADR-PR>`, PR `#<M1.2-PR>`, PR `#<M1.3-PR>` | `tests/test_quota_guard.py` | `brain-query` (`SK-3`) | [[youtube-api-quota-system]] |
| **`TBD-02`** Similarity Weights `0.65 / 0.25 / 0.10` + Missing-Tag Fallback (**Closed by ADR-004**) | `#20`, `#55` | PR `#<ADR-PR>`, PR `#57` | `tests/test_similarity.py` | `brain-query` (`SK-3`) | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] |
| **`TBD-03`** Cache TTLs: `cached_videos=24h`, `cached_channels=7d` (**Closed by ADR-002**) | `#20`, `#38`, `#39`, `#41` | PR `#<ADR-PR>`, PR `#<M1.1-PR>`, PR `#<M1.3-PR>` | `tests/test_repository.py` | `brain-query` (`SK-3`) | [[sqlite-wal-mode]] |
