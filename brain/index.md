---
title: "Second Brain Index"
author: "Pranay Sanjan Kanneti"
created: 2026-11-24
tags: [index, para, navigation]
type: index
---

# Second Brain — YouTube Video Intelligence MCP Server

Master table of contents and `[[wikilink]]` hub for team research, standards, and stage reviews.

## PARA Structure
- **Inbox (`brain/inbox/`)**: Unprocessed ingested notes and `ai-session` logs.
- **Projects (`brain/projects/`)**: Active milestones and stage deliverables.
- **Areas (`brain/areas/`)**: Ongoing engineering standards and policies.
- **Resources (`brain/resources/`)**: Distilled technical research notes (cited by ADRs and skills).
- **Archive (`brain/archive/`)**: Completed milestones and retired drafts.

## Core Vault Files
- [[log]]

## Projects
- [[srs-requirements-index]]
- [[stage-1-review]] — Stage 1 retrospective and actions for Stage 2.
- [[stage-2-review]] — Stage 2 architecture, design, and verification retrospective (`SB-2`)
## Inbox
- [[ai-session-2026-11-27-m2-4-provider-contract-tests]] — M2.4 mock/live contract, backoff, OAuth, and provider-isolation tests (Issue #49).
- [[ai-session-2026-11-27-m2-3-live-youtube-provider]] — M2.3 live YouTube provider, OAuth refresh, and bounded backoff (Issue #46).
- [[ai-session-2026-11-27-m2-2-fixture-mock-provider]] — M2.2 sanitized fixtures and full offline mock provider (Issue #45).
- [[ai-session-2026-11-27-m2-1-provider-contract]] — M2.1 typed provider models, exception hierarchy, and full provider ABC (Issue #44).
- [[ai-session-2026-11-24]] — Stage 1 vault setup and project scoping.
- [[ai-session-2026-11-26]] — Stage 2 AI session log covering ADRs `001`–`006`, `TBD-01`..`TBD-03`, and `SB-3` CI validation for Issue #20.
- [[ai-session-2026-11-27-m0-server-skeleton]] — Stage 2 AI session log for Milestone `M0.2` server skeleton, SQLite WAL, and `YouTubeProvider` boundary (Issue `#26`, PR `#33`).
- [[ai-session-2026-11-27]] — Stage 2 architecture/planning retrospective and M0.5 skill evaluations for Issue #29.

## Active Notes (Add links here as PRs merge)
- [[youtube-api-quota-system]]
- [[youtube-oauth2-flow]]
- [[sqlite-wal-mode]]
- [[provider-pattern-isolation]]
- [[mcp-architecture]] — MCP's host-client-server architecture, primitives, transports, and YouTube project integration.
- [[agent-skills-format-specification]] — Open skill directory, metadata, instruction, progressive-disclosure, and citation conventions.
- [[fastmcp-python-sdk]] — Python FastMCP tools, validation, structured results, error mapping, and ASGI integration.
- [[youtube-engagement-library-analytics]] — Channel/category distributions, duration metrics, time-series buckets, and period comparisons.
- [[iso-8601-duration-parsing-and-playlist-constraint-packing]] — Parse video durations and enforce playlist constraints before confirmation.
- [[prompt-injection-defense-for-untrusted-youtube-metadata]] — Keep YouTube metadata untrusted and require explicit playlist confirmation.
- [[tf-idf-cosine-similarity-for-video-and-channel-ranking]] — Compute deterministic similarity rankings from official metadata.
