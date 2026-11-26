# ADR-006: Pre-Flight Quota Guard and Soft Warning Threshold

- **ADR ID:** ADR-006
- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** YouTube MCP Team
- **Related Requirements:** SE-3, SB-3, TQ-6, CON-3, NFR-SAFE-1, REQ-DB-2, REQ-FR1-2, REQ-FR5-6, TBD-01
- **Related Issue:** #20

## Context
Google Cloud assigns a default quota of **10,000 units/day** per project (`CON-3`), and creating additional Google Cloud projects or rotating keys to obtain more quota is prohibited (`AGENTS.md`). Endpoint costs vary sharply:
- `videos.list`, `channels.list`, `playlistItems.list`, `playlists.list`, `subscriptions.list`: **1 unit** per call (up to 50 IDs per batch for `videos.list`).
- `playlists.insert`, `playlistItems.insert`: **50 units** per call.
- `search.list`: **100 units** per call.

Under `TQ-6` and `NFR-SAFE-1`, every uncached provider workflow must evaluate its worst-case unit cost against the SQLite `quota_ledger` (`REQ-DB-2`) *before* executing any outbound API call and reject execution with `QuotaBudgetExceededError` if `used_today + estimated_cost > daily_budget`. SRS `TBD-01` deferred deciding whether high-cost discovery workflows also require a per-workflow soft warning or pagination cap.

## Options Considered
- **Option A — Hard Daily Ceiling Only (No Per-Workflow Warning or Cap):**
  - *Pros:* Simplest pre-flight check (`used + estimated <= 10,000`).
  - *Cons:* A single uncached discovery or multi-page `search.list` workflow could consume thousands of units unexpectedly in one call before anyone notices, starving subsequent `FR-5` playlist writes (`50 + 50N` units) for the rest of the day.
- **Option B — Strict Low Hard Cap (Block Any Workflow Over 300 Units):**
  - *Pros:* Strongly protects daily quota.
  - *Cons:* Would block legitimate `FR-5` playlist creations of 6+ videos ($50 + 50 \times 6 = 350$ units) even when plenty of daily quota remains.
- **Option C — Hard Daily Budget Guard (`TQ-6`) + Per-Workflow Soft Warning & Discovery Pagination Guard (`TBD-01`):**
  - *Pros:* Guarantees `used + estimated <= 10,000` is never violated while surfacing early visibility when a single discovery workflow exceeds a configurable soft threshold, and capping uncached `search.list` fan-out cleanly.
  - *Cons:* Adds a `quota_warning` metadata field to discovery responses and an explicit `max_search_pages` cap.

## Decision
Implement an **atomic SQLite pre-flight quota guard** (`TQ-6`) paired with a **300-unit per-workflow soft warning threshold** and discovery pagination bound, **closing `TBD-01`**:
1. **Hard Pre-Flight Budget Gate (`TQ-6`, `NFR-SAFE-1`):**
   - Before any uncached `YouTubeProvider` call, compute worst-case `estimated_cost` from known endpoint unit costs (`search.list = 100`, `playlists.insert = 50`, `playlistItems.insert = 50`, list reads `= 1`), deducting cached hits already valid within their ADR-002 TTLs.
   - Inside an explicit SQLite transaction (`quota_ledger`, keyed by `date_utc`), compute `used_today = SUM(units_cost)`. If `used_today + estimated_cost > daily_budget` (default `10,000`), reject immediately with `QuotaBudgetExceededError` prior to any provider call (`REQ-FR1-2`, `REQ-FR5-6`).
   - Record actual endpoint costs in `quota_ledger` atomically with `workflow_context` and `created_at` (`REQ-DB-2`).
2. **Per-Workflow Soft Warning Threshold (Closes `TBD-01`):**
   - Set default `SOFT_WARNING_THRESHOLD_UNITS = 300` (configurable via server settings).
   - When an uncached discovery workflow (`FR-1`, `FR-2`, `FR-3`, or `FR-5` candidate gathering) estimates `estimated_cost > 300` units while still within the remaining daily budget, **allow execution** (do not hard-block legitimate requests) and attach a structured `quota_warning` message to the tool response noting estimated units and remaining daily quota.
   - Cap uncached `search.list` discovery at `max_search_pages = 2` (200 units max per discovery call) by default, preferring cached metadata and `videos.list` batching (up to 50 IDs for 1 unit) whenever possible.

## Consequences
- **Positive:**
  - Closes `TBD-01` with a concrete, non-breaking 300-unit soft warning threshold and bounded `search.list` pagination, preventing runaway discovery runs while preserving `FR-5` multi-track playlist writes.
  - Guarantees zero API calls are fired once daily quota would be exceeded (`TQ-6`).
- **Negative / Trade-offs:**
  - If Google returns `quotaExceeded` out-of-band (e.g., due to external console usage on the same project key), `LiveYouTubeProvider` must still catch the 403 error, raise `QuotaBudgetExceededError`, and optionally mark remaining local budget exhausted for `date_utc`.

## Citations (SB-3)
- [[youtube-api-quota-system]] (`brain/resources/youtube-api-quota-system.md`)
- [[sqlite-wal-mode]] (`brain/resources/sqlite-wal-mode.md`)
- [[provider-pattern-isolation]] (`brain/resources/provider-pattern-isolation.md`)
- [[srs-requirements-index]] (`brain/projects/srs-requirements-index.md`)
