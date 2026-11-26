# Architecture Decision Records (ADRs)

This directory documents Stage 2 architectural decisions for the **YouTube Video Intelligence MCP Server** (`SE-3`), grounded in distilled Second Brain research notes (`SB-3`) and traceable to [docs/srs.pdf](../srs.pdf) and [srs-requirements-index](../../brain/projects/srs-requirements-index.md).

Use [template.md](template.md) when authoring new ADRs.

## ADR Index

| ADR ID | Title | Status | Date | Related Requirements / TBDs Resolved |
|---|---|---|---|---|
| [ADR-001](001-python-fastmcp-and-fastapi-runtime.md) | Python 3.11+, FastMCP, and FastAPI Runtime | Accepted | 2026-11-26 | `SE-3`, `SE-7`, `SB-3`, `NFR-QUAL-4`, `FR-1`..`FR-5` |
| [ADR-002](002-sqlite-wal-storage-and-cache-ttl.md) | SQLite 3 WAL-Mode Storage and Metadata Cache TTL | Accepted | 2026-11-26 | `SE-3`, `SB-3`, `REQ-DB-1`..`REQ-DB-4`, `NFR-PERF-3`, `NFR-SAFE-3`, `TQ-6`, **Closes `TBD-03`** |
| [ADR-003](003-provider-interface-isolation.md) | Abstract `YouTubeProvider` Interface Isolation | Accepted | 2026-11-26 | `SE-3`, `SB-3`, `SE-6`, `TQ-4`, `TQ-5`, `NFR-QUAL-1`, `NFR-QUAL-2`, `NFR-PERF-1`, `NFR-SEC-1`, `NFR-SEC-4` |
| [ADR-004](004-similarity-scoring-and-weights.md) | Metadata Similarity Scoring and Feature Weight Calibration | Accepted | 2026-11-26 | `SE-3`, `SB-3`, `FR-1`, `FR-2`, `TQ-1`, `TQ-4`, `NFR-PERF-2`, **Closes `TBD-02`** |
| [ADR-005](005-two-phase-playlist-confirmation-and-prompt-injection.md) | Two-Phase Playlist Confirmation and Prompt-Injection Defense | Accepted | 2026-11-26 | `SE-3`, `SB-3`, `FR-5`, `NFR-SAFE-2`, `NFR-SEC-2`, `TQ-4`, `SK-5` |
| [ADR-006](006-preflight-quota-guard-and-warning-threshold.md) | Pre-Flight Quota Guard and Soft Warning Threshold | Accepted | 2026-11-26 | `SE-3`, `SB-3`, `TQ-6`, `CON-3`, `NFR-SAFE-1`, `REQ-DB-2`, `REQ-FR1-2`, `REQ-FR5-6`, **Closes `TBD-01`** |
