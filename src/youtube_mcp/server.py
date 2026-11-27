"""FastMCP and FastAPI server entrypoint (`ADR-001`, `SE-7`).

All diagnostic logs are routed exclusively to `stderr` so MCP `stdio` JSON-RPC
framing on `stdout` is never corrupted.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from youtube_mcp import __version__
from youtube_mcp.config import Settings, load_settings
from youtube_mcp.db import check_wal_health, init_db
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.providers.mock import FixtureMockProvider

SERVICE_NAME = "youtube-video-intelligence-mcp"

logger = logging.getLogger(__name__)


def configure_logging(level: str = "INFO") -> None:
    """Route application logging strictly to `stderr`, never `stdout`."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any accidental stdout stream handlers to keep MCP stdio clean.
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            root_logger.removeHandler(handler)

    has_stderr_handler = any(
        isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr
        for handler in root_logger.handlers
    )
    if not has_stderr_handler:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(numeric_level)
        stderr_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        root_logger.addHandler(stderr_handler)


class HealthResponse(BaseModel):
    """Read-only HTTP health check payload (`docs/architecture.md` §6.3)."""

    status: str
    service: str
    version: str
    journal_mode: str
    daily_quota_budget: int
    remaining_quota: int


mcp = FastMCP(SERVICE_NAME)


def create_app(
    settings: Settings | None = None,
    provider: YouTubeProvider | None = None,
) -> FastAPI:
    """Create the FastAPI ASGI application hosting HTTP health/OpenAPI and FastMCP."""
    resolved_settings = settings or load_settings()
    resolved_provider = provider or FixtureMockProvider()
    app_mcp = FastMCP(SERVICE_NAME)
    app_mcp.settings.streamable_http_path = "/"

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings.log_level)
        init_db(resolved_settings.db_path)
        logger.info(
            "Initialized SQLite WAL database at %s",
            resolved_settings.db_path,
        )
        fastapi_app.state.settings = resolved_settings
        fastapi_app.state.provider = resolved_provider
        async with app_mcp.session_manager.run():
            yield

    fastapi_app = FastAPI(
        title="YouTube Video Intelligence MCP Server",
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    fastapi_app.state.settings = resolved_settings
    fastapi_app.state.provider = resolved_provider

    @fastapi_app.get(
        "/api/v1/health",
        response_model=HealthResponse,
        tags=["health"],
        summary="Read-only server, SQLite WAL, and daily quota health check",
    )
    def health(request: Request) -> HealthResponse | JSONResponse:
        active_settings: Settings = request.app.state.settings
        try:
            try:
                wal_status = check_wal_health(
                    daily_quota_budget=active_settings.daily_quota_budget,
                    db_path=active_settings.db_path,
                )
            except sqlite3.OperationalError as exc:
                if "no such table" not in str(exc).lower():
                    raise
                init_db(active_settings.db_path)
                wal_status = check_wal_health(
                    daily_quota_budget=active_settings.daily_quota_budget,
                    db_path=active_settings.db_path,
                )
        except (sqlite3.Error, OSError) as exc:
            logger.error("Health check failed accessing SQLite: %s", exc)
            degraded = HealthResponse(
                status="degraded",
                service=SERVICE_NAME,
                version=__version__,
                journal_mode="unavailable",
                daily_quota_budget=active_settings.daily_quota_budget,
                remaining_quota=0,
            )
            return JSONResponse(status_code=503, content=degraded.model_dump())

        journal_mode = str(wal_status["journal_mode"]).lower()
        payload = HealthResponse(
            status="ok" if journal_mode == "wal" else "degraded",
            service=SERVICE_NAME,
            version=__version__,
            journal_mode=journal_mode,
            daily_quota_budget=int(wal_status["daily_quota_budget"]),
            remaining_quota=int(wal_status["remaining_quota"]),
        )
        if journal_mode != "wal":
            return JSONResponse(status_code=503, content=payload.model_dump())
        return payload

    fastapi_app.mount("/mcp", app_mcp.streamable_http_app())

    return fastapi_app


app = create_app()


def main() -> None:
    """Run the MCP server over `stdio` transport with `stderr`-only logging."""
    settings = load_settings()
    configure_logging(settings.log_level)
    init_db(settings.db_path)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
