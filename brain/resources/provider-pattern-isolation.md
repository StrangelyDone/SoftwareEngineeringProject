---
title: "Provider Pattern Isolation for Offline Fixture Testing"
author: "Pranay Sanjan Kanneti"
created: 2026-11-26
tags: [youtube-mcp, resource, providers, testing]
type: resource
---

# Provider Pattern Isolation for Offline Fixture Testing

## Summary
Keep YouTube Data API and OAuth network operations behind provider interfaces, separate from application logic. Production adapters use the official YouTube Data API, while tests inject fixture-backed providers that return recorded responses without contacting YouTube. This supports deterministic CI and avoids consuming live API quota.

## Key Technical Details
- **Boundary:** Place YouTube API and OAuth adapters behind provider interfaces in `src/providers/`; application services depend on the interface rather than constructing external clients directly.
- **Offline tests:** Inject a fake provider backed by recorded, sanitized fixtures or controlled mocks. Test application behavior and error handling without live YouTube API calls.
- **Contract consistency:** Keep fixture responses aligned with the provider's expected data and error shapes; cover relevant cases such as unavailable resources, expired authorization, rate limits, and `quotaExceeded`.
- **Quota safety:** CI tests use fixtures/mocks rather than live requests, as required by `TQ-5`; production quota preflight remains a separate responsibility under `TQ-6`.

## Project Traceability & Connections
- **Related Requirements:** SE-6, TQ-4, TQ-5, TQ-6
- **Related Notes:** [[index]], [[youtube-api-quota-system]], [[sqlite-wal-mode]], [[youtube-oauth2-flow]]
- **Source:** Project contract in `AGENTS.md` (provider isolation, offline CI testing, and quota requirements); [[youtube-api-quota-system]]
