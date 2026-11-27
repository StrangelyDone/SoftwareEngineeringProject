## [0.2.0-stage2] - 2026-11-27

### Added
- **Agent Skills (`SK-2`, `SK-3`, `SK-4`):** Implemented `.agents/skills/brain-refine/SKILL.md`, `.agents/skills/brain-query/SKILL.md`, and `.agents/skills/local-check/SKILL.md` with local verification runner.
- **Architecture Decision Records (`SE-3`, `SB-3`):** Added `docs/adr/001` through `docs/adr/006` locking runtime (`FastMCP` + `FastAPI`), SQLite WAL storage + 24h/7d cache TTLs (closing `TBD-03`), `YouTubeProvider` isolation (`SE-6`), TF-IDF similarity weights `0.65 / 0.25 / 0.10` (closing `TBD-02`), two-phase playlist confirmation + prompt-injection defense (`FR-5`), and pre-flight quota guard + 300-unit soft warning (closing `TBD-01`).
- **System Architecture & Planning (`SE-2`, `SE-4`, `SE-5`):** Added `docs/architecture.md` (layered component, SQLite ER, UML class, and 3 sequence diagrams + 6 MCP tool contracts + exception hierarchy), `docs/development-plan.md`, and live `docs/traceability-matrix.md`.
- **Runnable Server Skeleton (`SE-6`, `SE-7`, `REQ-DB-1`):** Scaffolded `src/youtube_mcp/` (`config.py`, `db.py` in WAL mode with 4 tables, abstract `YouTubeProvider`, `FixtureMockProvider` stub, and `FastAPI`/`FastMCP` server with `GET /api/v1/health` and `/openapi.json`).
- **Offline Verification & Skill Evals (`TQ-5`, `TQ-7`):** Added offline `tests/test_db_wal.py` and `tests/test_health.py`, pinned dependencies in `pyproject.toml`, and documented all 4 active skill evaluation runs in `docs/test-results.md`.
- **Governance & Retrospective (`SB-2`):** Added Stage 2 AI session log and `brain/projects/stage-2-review.md`.

### Changed
- Graduated Stage 1 research notes from `brain/inbox/` into `brain/resources/` via `brain-refine` and synchronized `brain/index.md` and `brain/log.md`.
