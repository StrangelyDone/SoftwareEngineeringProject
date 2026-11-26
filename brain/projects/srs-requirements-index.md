---
title: "SRS Requirements Index"
author: "StrangelyDone"
created: 2026-11-26
tags: [youtube-mcp, srs, requirements, stage-1]
type: project
---

# SRS Requirements Index

Concise Stage 1 traceability from the Software Requirements Specification to existing Second Brain research notes. Links below point only to notes already present in `brain/`; `[[index]]` indicates there is no more specific distilled note yet.

**Canonical SRS:** [docs/srs.pdf](../../docs/srs.pdf)

## Functional Requirements

| ID | Requirement | Existing brain note(s) |
|---|---|---|
| FR-1 | Rank similar videos using metadata | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] |
| FR-2 | Rank similar channels using metadata | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] |
| FR-3 | Recommend unseen videos using authorized library data | [[youtube-oauth2-flow]], [[youtube-engagement-library-analytics]], [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] |
| FR-4 | Analyze engagement, library distributions, trends, durations, and period changes | [[youtube-engagement-library-analytics]] |
| FR-5 | Curate constrained playlists and create them only after confirmation | [[iso-8601-duration-parsing-and-playlist-constraint-packing]], [[prompt-injection-defense-for-untrusted-youtube-metadata]] |

## Non-Functional Requirements

| ID | Requirement area | Existing brain note(s) |
|---|---|---|
| NFR-PERF-1 | Offline CI suite completes within 15 seconds | [[provider-pattern-isolation]] |
| NFR-PERF-2 | Similarity ranking of up to 200 cached videos completes within 500 ms | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] |
| NFR-PERF-3 | Cached metadata reads avoid repeat API quota cost | [[sqlite-wal-mode]], [[youtube-api-quota-system]] |
| NFR-SAFE-1 | Reject workflows exceeding remaining quota before provider calls | [[youtube-api-quota-system]] |
| NFR-SAFE-2 | Restrict account mutations to safe playlist creation/appends | [[mcp-architecture]], [[prompt-injection-defense-for-untrusted-youtube-metadata]] |
| NFR-SAFE-3 | Protect SQLite state with ACID transactions | [[sqlite-wal-mode]] |
| NFR-SEC-1 | Isolate credentials and keep secrets out of Git, logs, and AI tools | [[youtube-oauth2-flow]], [[prompt-injection-defense-for-untrusted-youtube-metadata]] |
| NFR-SEC-2 | Treat retrieved YouTube metadata as untrusted input | [[prompt-injection-defense-for-untrusted-youtube-metadata]] |
| NFR-SEC-3 | Run automated secret scanning for pull requests | [[prompt-injection-defense-for-untrusted-youtube-metadata]] (related security note; no dedicated scanning note yet) |
| NFR-SEC-4 | Keep personal data out of committed test fixtures | [[prompt-injection-defense-for-untrusted-youtube-metadata]] |
| NFR-QUAL-1 | Isolate external API calls behind a provider interface | [[provider-pattern-isolation]] |
| NFR-QUAL-2 | Handle rate limits, transient errors, and typed provider failures | [[provider-pattern-isolation]], [[youtube-api-quota-system]] |
| NFR-QUAL-3 | Require clean Python lint and formatting checks in CI | [[index]] (no dedicated linting note yet) |
| NFR-QUAL-4 | Keep MCP tool schemas interoperable with JSON Schema and MCP | [[mcp-architecture]], [[fastmcp-python-sdk]] |

## Agent Skill Requirements

| ID | Requirement area | Existing brain note(s) |
|---|---|---|
| SK-1 | Ingest research and session material into the Second Brain | [[agent-skills-format-specification]], [[index]] |
| SK-2 | Refine the vault by sorting notes, deduplicating, and repairing links | [[agent-skills-format-specification]], [[index]] |
| SK-3 | Query saved notes for technical answers and project documents | [[index]] (no dedicated query-workflow note yet) |
| SK-4 | Run local build, tests, server startup, and health check | [[fastmcp-python-sdk]], [[mcp-architecture]] |
| SK-5 | Run the video-to-playlist workflow with user confirmation | [[iso-8601-duration-parsing-and-playlist-constraint-packing]], [[prompt-injection-defense-for-untrusted-youtube-metadata]] |

## Testing and Quality Requirements

| ID | Requirement area | Existing brain note(s) |
|---|---|---|
| TQ-1 | Unit tests for ranking, duration handling, playlist selection, and MCP serialization | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]], [[iso-8601-duration-parsing-and-playlist-constraint-packing]], [[fastmcp-python-sdk]] |
| TQ-2 | Integration tests across services, SQLite WAL, and providers | [[provider-pattern-isolation]], [[sqlite-wal-mode]] |
| TQ-3 | End-to-end tests for FR-1 through FR-5 over MCP | [[mcp-architecture]], [[fastmcp-python-sdk]] |
| TQ-4 | Negative and edge-case tests for API, auth, and invalid data | [[youtube-oauth2-flow]], [[prompt-injection-defense-for-untrusted-youtube-metadata]], [[youtube-engagement-library-analytics]] |
| TQ-5 | Keep pull-request CI on fixtures/mocks; isolate live API tests | [[provider-pattern-isolation]], [[youtube-api-quota-system]] |
| TQ-6 | Verify quota budgets before provider execution | [[youtube-api-quota-system]], [[sqlite-wal-mode]] |
| TQ-7 | Evaluate all skills and record pass/fail results before stage submissions | [[agent-skills-format-specification]], [[index]] |
| TQ-8 | Log significant defects and add permanent regression tests | [[provider-pattern-isolation]], [[stage-1-review]] |

## Stage 2 Open Decisions

| ID | Deferred decision | Existing brain note(s) |
|---|---|---|
| TBD-01 | Whether high-cost workflows need a soft quota warning or pagination threshold | [[youtube-api-quota-system]] |
| TBD-02 | Calibrate TF-IDF, tag-overlap, and category-match weights using fixtures | [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] |
| TBD-03 | Choose the SQLite video/channel metadata cache TTL | [[sqlite-wal-mode]], [[youtube-api-quota-system]] |

## Traceability & Connections

- **Related Notes:** [[index]], [[stage-1-review]]
- **Source:** [Canonical SRS PDF](../../docs/srs.pdf); repository test and architecture references in `AGENTS.md`.
