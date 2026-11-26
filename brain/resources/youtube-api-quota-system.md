---
title: "YouTube Data API v3 Quota System"
author: "Pranay Sanjan Kanneti"
created: 2026-11-24
tags: [research, youtube-api, quota, constraints]
type: resource
---

# YouTube Data API v3 Quota System

## Key Facts
- Default quota for a new Google Cloud project is **10,000 units per day**.
- Creating extra Google Cloud projects to obtain additional quota is strictly prohibited.
- Endpoint unit costs:
  - `search.list`: **100 units** per call (high cost).
  - `playlists.insert`: **50 units** per call.
  - `videos.list`: **1 unit** per call (low cost).

## System Design Implications
- **Pre-call Budget Guard (`TQ-6`)**: Track quota cost per request in local storage (see `[[sqlite-wal-mode]]`) and reject workflows that would exceed the remaining daily budget *before* executing any outbound HTTP call.
- **Offline CI Testing (`TQ-5`)**: Automated CI test suites must run against recorded fixtures/mocks via a provider interface (see `[[provider-pattern-isolation]]`) instead of burning live quota.
- **Caching**: Cache video and channel metadata aggressively to avoid redundant fetches.

## Traceability & Links
- Requirements: `FR-1`, `FR-5`, `TQ-5`, `TQ-6`
- Related Notes: `[[provider-pattern-isolation]]`, `[[sqlite-wal-mode]]`, `[[youtube-oauth2-flow]]`