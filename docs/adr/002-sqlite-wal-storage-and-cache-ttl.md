# ADR-002: SQLite 3 WAL-Mode Storage and Metadata Cache TTL

- **ADR ID:** ADR-002
- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** YouTube MCP Team
- **Related Requirements:** SE-3, SB-3, REQ-DB-1, REQ-DB-2, REQ-DB-3, REQ-DB-4, NFR-PERF-3, NFR-SAFE-3, TQ-6, TBD-03
- **Related Issue:** #20

## Context
The server requires durable local state for four core responsibilities defined in `docs/srs.pdf` (`REQ-DB-1` through `REQ-DB-4`):
1. **`quota_ledger`**: Atomic daily quota accounting (`id`, `date_utc`, `endpoint`, `units_cost`, `workflow_context`, `created_at`) for pre-flight budget enforcement (`TQ-6`).
2. **`cached_videos` & `cached_channels`**: Local metadata caching (`fetched_at` timestamps + serialized metadata payloads) so repeated lookups incur zero YouTube API quota cost (`NFR-PERF-3`) and similarity ranking over up to 200 cached videos meets `<500 ms` latency (`NFR-PERF-2`).
3. **`pending_playlists`**: Durable two-phase curation state (`confirmation_token` primary key, `topic`, `constraints_json`, `selected_video_ids_json`, `total_duration_seconds`, `estimated_quota_cost`, `status`, `expires_at`) for `FR-5`.

Additionally, SRS `TBD-03` deferred choosing the exact metadata cache expiration window (TTL) for `cached_videos` and `cached_channels` to Stage 2.

## Options Considered
- **Option A — In-Memory Python Dictionaries / JSON Flat Files:**
  - *Pros:* Simple initial implementation with zero schema setup.
  - *Cons:* Volatile across server restarts (losing `quota_ledger` history and `pending_playlists` tokens), lacks ACID rollback guarantees (`NFR-SAFE-3`), and risks race conditions when HTTP health checks and MCP tool calls read/write concurrently.
- **Option B — External Database Server (PostgreSQL / Redis):**
  - *Pros:* Full multi-host concurrency and built-in TTL expiration (`Redis`).
  - *Cons:* Adds heavy external infrastructure for a local-first `127.0.0.1` / `stdio` MCP server, complicates `local-check` (`SK-4`) and offline CI (`TQ-5`), and violates the lightweight single-host project design.
- **Option C — Embedded SQLite 3 in WAL Mode (`PRAGMA journal_mode=WAL;`) with Explicit Cache TTLs:**
  - *Pros:* Zero-ops embedded engine included in Python's standard library (`sqlite3`), supports concurrent readers alongside a writer without blocking, guarantees ACID transactions (`NFR-SAFE-3`), and keeps all four tables co-located in one local database file.
  - *Cons:* Single-writer serialization requires `PRAGMA busy_timeout=5000;` and local filesystem placement (network filesystems are unsupported due to `-wal`/`-shm` sidecar files).

## Decision
Adopt **SQLite 3 in Write-Ahead Logging (WAL) mode** (`REQ-DB-1`..`REQ-DB-4`) and **close `TBD-03`** with concrete table-specific cache TTLs:
1. **Connection Pragmas (`REQ-DB-1`):** Every connection opens on a local filesystem path and executes `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=5000;`, and `PRAGMA foreign_keys=ON;`. All mutations to `quota_ledger`, `cached_videos`, `cached_channels`, and `pending_playlists` execute inside explicit ACID transactions (`NFR-SAFE-3`).
2. **Metadata Cache TTLs (Closes `TBD-03`):**
   - **`cached_videos` TTL = 24 hours (86,400 seconds):** Video titles, descriptions, tags, durations, and `statistics` (`viewCount`, `likeCount`) change moderately quickly; a 24-hour TTL keeps `FR-1`/`FR-4`/`FR-5` metadata fresh while eliminating redundant `videos.list` calls within daily workflows (`NFR-PERF-3`).
   - **`cached_channels` TTL = 7 days (604,800 seconds):** Channel branding, `topicDetails`, and `relatedPlaylists.uploads` IDs change infrequently; a 7-day TTL avoids repeated `channels.list` calls while letting recent uploads refresh via `playlistItems.list` when needed (`FR-2`).
   - **Cache Lookup Rule:** Entries where `(now_utc - fetched_at) < TTL` are served directly from SQLite at 0 quota units; stale entries are refreshed transparently via `YouTubeProvider` after passing the `TQ-6` pre-flight check.

## Consequences
- **Positive:**
  - Read-only `GET /api/v1/health` queries and cached similarity reads run concurrently without blocking or being blocked by ledger/playlist writes.
  - Explicit 24h (`cached_videos`) and 7d (`cached_channels`) TTLs formally close `TBD-03`, preserving quota while bounding metadata staleness.
- **Negative / Trade-offs:**
  - SQLite database files (and `-wal`/`-shm` sidecars) must reside on a local disk, never on a network filesystem (`NFS`/`SMB`).
  - Stale-row cleanup or lazy overwrite on miss is required so the cache file does not grow unbounded over long deployments, and long-lived read transactions must be avoided so WAL auto-checkpointing (~1,000 pages) is not delayed.

## Citations (SB-3)
- [[sqlite-wal-mode]] (`brain/resources/sqlite-wal-mode.md`)
- [[youtube-api-quota-system]] (`brain/resources/youtube-api-quota-system.md`)
- [[srs-requirements-index]] (`brain/projects/srs-requirements-index.md`)
