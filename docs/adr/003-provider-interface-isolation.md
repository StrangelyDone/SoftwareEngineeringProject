# ADR-003: Abstract `YouTubeProvider` Interface Isolation

- **ADR ID:** ADR-003
- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** YouTube MCP Team
- **Related Requirements:** SE-3, SB-3, SE-6, TQ-4, TQ-5, NFR-QUAL-1, NFR-QUAL-2, NFR-PERF-1, NFR-SEC-1, NFR-SEC-4
- **Related Issue:** #20

## Context
Every functional requirement (`FR-1`..`FR-5`) depends on official YouTube Data API v3 endpoints (`videos.list`, `channels.list`, `playlistItems.list`, `search.list`, `subscriptions.list`, `playlists.list`, `playlists.insert`, `playlistItems.insert`) and Google OAuth 2.0 credentials for personalized/write operations. At the same time:
- `SE-6` and `NFR-QUAL-1` require 100% of external API and OAuth calls to be isolated behind an abstract provider boundary.
- `TQ-5` prohibits live YouTube API calls in CI and requires the full offline test suite to execute in under 15 seconds (`NFR-PERF-1`).
- `TQ-4` requires deterministic testing of error states—malformed IDs, private/deleted videos (`VideoUnavailableError`), missing tags, `quotaExceeded`, `youtubeSignupRequired` (Google account lacking a YouTube channel), expired 7-day Testing-mode refresh tokens, and HTTP 429 / 5xx retries (`NFR-QUAL-2`).
- `CON-1` forbids any scraping or unofficial libraries (`yt-dlp`, `pytube`).

## Options Considered
- **Option A — Direct `googleapiclient` / `httpx` Calls Inside MCP Tools & Domain Services (Patched in Tests with `monkeypatch`):**
  - *Pros:* Slightly fewer files initially.
  - *Cons:* Couples domain logic (TF-IDF ranking, duration knapsack, quota math) directly to HTTP transport and Google SDK shapes, makes `monkeypatch` tests brittle, and violates `SE-6` / `NFR-QUAL-1`.
- **Option B — Abstract `YouTubeProvider` Interface with `LiveYouTubeProvider` and `FixtureMockProvider`:**
  - *Pros:* Clean architectural seam in `src/youtube_mcp/providers/`; domain services depend solely on typed provider methods and domain exceptions; offline CI exercises `FixtureMockProvider` over sanitized JSON fixtures (`NFR-SEC-4`) in milliseconds (`NFR-PERF-1`) without burning the 10,000-unit daily quota (`TQ-5`).
  - *Cons:* Requires maintaining strict parity between recorded fixtures and live API response models.

## Decision
Isolate 100% of YouTube Data API v3 and Google OAuth 2.0 interactions behind an abstract `YouTubeProvider` base class (`abc.ABC` / `Protocol`) inside `src/youtube_mcp/providers/`:
1. **Provider Contract (`SE-6`):** Domain services (`similarity`, `analytics`, `curation`, `quota_guard`) and FastMCP handlers accept a `YouTubeProvider` dependency and never import `googleapiclient`, `google-auth`, or HTTP client libraries directly.
2. **Concrete Adapters:**
   - **`LiveYouTubeProvider` (Live Runtime):** Implements official YouTube Data API v3 calls (`CON-1`) and OAuth 2.0 offline-access token management (`access_type=offline`), loads secrets strictly from environment variables / git-ignored credential files (`NFR-SEC-1`), applies bounded exponential backoff with jitter on HTTP 429 / transient 5xx (`NFR-QUAL-2`), and maps API errors (`quotaExceeded`, `youtubeSignupRequired`, `videoNotFound`, expired 7-day Testing refresh tokens) to typed domain exceptions (`TQ-4`).
   - **`FixtureMockProvider` (Offline CI & Local Tests):** Loads sanitized JSON fixtures from `tests/fixtures/` (`NFR-SEC-4` — zero PII or live tokens) and supports deterministic fault injection for `TQ-4` negative tests (`TQ-5`).
3. **Minimal Scopes & Non-Destructive Boundary (`NFR-SAFE-2`):** `LiveYouTubeProvider` requests only the minimum required YouTube scopes (`youtube.readonly` for `FR-3`/`FR-4`; `youtube` or `youtube.force-ssl` only when playlist creation under `FR-5` is configured) and exposes no methods for deleting videos, deleting playlists, or mutating subscriptions.

## Consequences
- **Positive:**
  - Full offline CI test suite runs deterministically in `<15s` with zero API quota consumption (`TQ-5`, `NFR-PERF-1`).
  - Edge cases that are hard to trigger reliably against live servers (HTTP 429, 7-day Testing refresh-token expiry, `youtubeSignupRequired`, `quotaExceeded`) are systematically verified in CI (`TQ-4`).
- **Negative / Trade-offs:**
  - Any schema change in `YouTubeProvider` requires updating both `LiveYouTubeProvider` and `FixtureMockProvider` plus fixture payloads to prevent mock drift.

## Citations (SB-3)
- [[provider-pattern-isolation]] (`brain/resources/provider-pattern-isolation.md`)
- [[youtube-oauth2-flow]] (`brain/resources/youtube-oauth2-flow.md`)
- [[youtube-api-quota-system]] (`brain/resources/youtube-api-quota-system.md`)
