# ADR-001: Python 3.11+, FastMCP, and FastAPI Runtime

- **ADR ID:** ADR-001
- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** YouTube MCP Team
- **Related Requirements:** SE-3, SE-7, SB-3, NFR-QUAL-4, FR-1, FR-2, FR-3, FR-4, FR-5, SK-4
- **Related Issue:** #20

## Context
The YouTube Video Intelligence MCP Server must expose five core functional capabilities (`FR-1` through `FR-5`) to AI hosts such as Claude Desktop over the Model Context Protocol (`MCP`) using JSON-RPC 2.0 (`stdio` for local host subprocess launches and Streamable HTTP for network/local verification). Simultaneously, `SE-7` requires an HTTP/1.1 interface bound to `127.0.0.1` (default port `8000`) exposing `GET /api/v1/health` (returning read-only service status and remaining daily quota for `local-check` / `SK-4`) and `GET /openapi.json` (`NFR-QUAL-4`).

The repository already uses Python 3.11+, `pyproject.toml`, `ruff`, and `pytest` (`AGENTS.md`, `NFR-QUAL-3`), and needs a single coherent server runtime inside `src/youtube_mcp/server.py` that keeps protocol boilerplate low while guaranteeing strict JSON Schema Draft 2020-12 input/output validation.

## Options Considered
- **Option A — Node.js / TypeScript MCP SDK + Express:**
  - *Pros:* First-party TypeScript MCP SDK support and mature HTTP middleware.
  - *Cons:* Splits the repository across two language ecosystems, duplicates validation and dependency management alongside Python tooling (`ruff`, `pytest`, `validate_brain.py`), and forces custom bridges for Python text-processing and SQLite workflows.
- **Option B — Raw Python JSON-RPC 2.0 Handler over `asyncio` / Stdout + Custom HTTP Server:**
  - *Pros:* Zero external SDK dependencies.
  - *Cons:* High maintenance burden to track MCP specification lifecycle handshakes, Streamable HTTP / SSE framing, JSON Schema generation, and OpenAPI spec generation, increasing risk of `NFR-QUAL-4` interoperability drift.
- **Option C — Python 3.11+ with `FastMCP` (`mcp>=1.28,<2`) + `FastAPI` ASGI Composition:**
  - *Pros:* Native Python 3.11+ typing (`BaseModel`, `TypedDict`, type annotations) generates MCP tool schemas automatically via `@mcp.tool()` and `@mcp.resource()`, supports both `stdio` and `mcp.streamable_http_app()` ASGI mounting, and pairs cleanly with `FastAPI` to serve `GET /api/v1/health` and `GET /openapi.json` from one process.
  - *Cons:* Requires pinning the MCP Python SDK to the `1.x` line (`mcp>=1.28,<2`) because `v2` renames `FastMCP` to `MCPServer`.

## Decision
Adopt **Python 3.11+**, **FastMCP** (`from mcp.server.fastmcp import FastMCP`, pinned to `mcp>=1.28,<2`), and **FastAPI** composed as a single ASGI application in `src/youtube_mcp/server.py`:
1. **MCP Capability Surface (`FR-1`..`FR-5`):** Register tools and resources on `FastMCP` using strict Pydantic/annotated Python schemas so arguments and structured outputs are validated automatically against JSON Schema Draft 2020-12 (`NFR-QUAL-4`). Map domain exceptions (`QuotaBudgetExceededError`, `VideoUnavailableError`, `ConfirmationRequiredError`, `InvalidVideoIdentifierError`) to `ToolError` or `CallToolResult(isError=True)` with concise remediation text and zero stack traces or credentials.
2. **Transports:** Support `stdio` transport (ensuring diagnostics go strictly to `stderr` so `stdout` carries only newline-delimited JSON-RPC messages) for Claude Desktop and CLI clients, and Streamable HTTP (`mcp.streamable_http_app()`) mounted into the `FastAPI` ASGI host.
3. **HTTP Health & OpenAPI (`SE-7`):** Expose `GET /api/v1/health` and `GET /openapi.json` via `FastAPI` bound to `127.0.0.1:8000` by default. Health responses are strictly read-only and never count as MCP tools or consume YouTube API quota.

## Consequences
- **Positive:**
  - Unified Python 3.11+ stack across domain services, SQLite repositories, FastMCP tools, FastAPI HTTP routes, `ruff` linting, and `pytest` offline suites.
  - Automatic JSON Schema and OpenAPI 3.x generation reduces schema drift across MCP clients and `SE-7` HTTP verification.
- **Negative / Trade-offs:**
  - Dependency constraint `mcp>=1.28,<2` must be maintained in `pyproject.toml` until an intentional migration to SDK `v2` (`MCPServer`) is scheduled.
  - Developers must keep `stdout` completely clean in `stdio` mode by routing all structured logs to `stderr`.

## Citations (SB-3)
- [[mcp-architecture]] (`brain/resources/mcp-architecture.md`)
- [[fastmcp-python-sdk]] (`brain/resources/fastmcp-python-sdk.md`)
- [[srs-requirements-index]] (`brain/projects/srs-requirements-index.md`)
