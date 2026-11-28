"""FastMCP and FastAPI server entrypoint (`ADR-001`, `SE-7`).

All diagnostic logs are routed exclusively to `stderr` so MCP `stdio` JSON-RPC
framing on `stdout` is never corrupted.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field

from youtube_mcp import __version__
from youtube_mcp.config import Settings, load_settings
from youtube_mcp.db import check_wal_health
from youtube_mcp.exceptions import ConfirmationRequiredError, YouTubeMCPError
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.providers.live import LiveYouTubeProvider
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.quota_guard import QuotaGuard
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.sanitizer import MetadataSanitizer
from youtube_mcp.services import (
    AnalyticsService,
    PlaylistCreatedResponse,
    PlaylistProposalRequest,
    PlaylistProposalResponse,
    PlaylistService,
    RecommendationService,
    RecommendationsResponse,
    SimilarChannelsResponse,
    SimilarityService,
    SimilarVideosResponse,
)
from youtube_mcp.services.analytics import EngagementReport

SERVICE_NAME = "youtube-video-intelligence-mcp"
logger = logging.getLogger(__name__)


def configure_logging(level: str = "INFO") -> None:
    """Route all root-logger output to `stderr`, never `stdout`."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )


class HealthResponse(BaseModel):
    """Read-only HTTP health check payload (`docs/architecture.md` §6.3)."""

    status: str
    service: str
    version: str
    journal_mode: str
    daily_quota_budget: int
    remaining_quota: int


class _ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolErrorPayload(BaseModel):
    """Safe error shape exposed to MCP clients."""

    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str
    remediation: str


class SimilarVideosInput(_ToolInput):
    video_ref: str = Field(min_length=1, max_length=2048)
    limit: int = Field(default=10, ge=1, le=25)


class SimilarChannelsInput(_ToolInput):
    channel_ref: str = Field(min_length=1, max_length=2048)
    limit: int = Field(default=10, ge=1, le=20)


class RecommendationsInput(_ToolInput):
    limit: int = Field(default=10, ge=1, le=25)
    exclude_known_videos: Literal[True] = True


class EngagementInput(_ToolInput):
    period_days: int = Field(default=30, ge=7, le=365)
    compare_previous_period: bool = True


class ProposePlaylistInput(_ToolInput):
    topic: str = Field(min_length=1, max_length=150)
    max_total_duration_minutes: int = Field(ge=5, le=600)
    max_video_duration_minutes: int | None = Field(default=None, ge=1, le=240)
    language: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")


class ConfirmPlaylistInput(_ToolInput):
    confirmation_token: str = Field(min_length=1, max_length=256)
    user_confirmed: bool = False
    playlist_title: str = Field(min_length=1, max_length=150)
    playlist_description: str = Field(default="", max_length=5000)
    privacy_status: Literal["private", "unlisted", "public"] = "private"


VideoRef = Annotated[str, Field(min_length=1, max_length=2048)]
ChannelRef = Annotated[str, Field(min_length=1, max_length=2048)]
VideoLimit = Annotated[int, Field(ge=1, le=25)]
ChannelLimit = Annotated[int, Field(ge=1, le=20)]
PeriodDays = Annotated[int, Field(ge=7, le=365)]
Topic = Annotated[str, Field(min_length=1, max_length=150)]
PlaylistTotalMinutes = Annotated[int, Field(ge=5, le=600)]
PlaylistVideoMinutes = Annotated[int, Field(ge=1, le=240)]
ConfirmationToken = Annotated[str, Field(min_length=1, max_length=256)]
PlaylistTitle = Annotated[str, Field(min_length=1, max_length=150)]
PlaylistDescription = Annotated[str, Field(max_length=5000)]
LanguageCode = Annotated[str, Field(pattern=r"^[A-Za-z]{2}$")]


def _tool_error_result(payload: dict[str, str]) -> CallToolResult:
    """Create an MCP error result while preserving FastMCP's typed output validation."""
    return CallToolResult(
        isError=True,
        content=[
            TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False),
            )
        ],
        structuredContent={"result": payload},
    )


def _map_tool_errors(tool_name: str, operation: Callable[[], Any]) -> Any:
    """Return safe structured MCP errors for domain and unexpected tool failures."""
    try:
        return operation()
    except YouTubeMCPError as exc:
        return _tool_error_result(exc.to_error_payload())
    except Exception:
        logger.exception("Unexpected error while executing MCP tool %s", tool_name)
        return _tool_error_result(
            {
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred while processing the request.",
                "remediation": "Check the request and try again. Contact support if the issue persists.",
            }
        )


@dataclass(frozen=True)
class ServerDependencies:
    """Fully wired persistence, provider, quota, and M3 domain services."""

    settings: Settings
    repository: SQLiteRepository
    provider: YouTubeProvider
    quota_guard: QuotaGuard
    similarity: SimilarityService
    recommendations: RecommendationService
    analytics: AnalyticsService
    playlists: PlaylistService


def _configured_provider(settings: Settings) -> YouTubeProvider:
    """Use the live adapter only when a YouTube credential is explicitly configured."""
    has_live_credentials = any(
        (
            settings.youtube_api_key,
            settings.youtube_oauth_client_id,
            settings.youtube_oauth_client_secret,
            settings.youtube_oauth_token_path,
        )
    )
    if not has_live_credentials:
        return FixtureMockProvider()

    return LiveYouTubeProvider(
        api_key=(
            settings.youtube_api_key.get_secret_value()
            if settings.youtube_api_key is not None
            else None
        ),
        oauth_credentials_path=settings.youtube_oauth_token_path,
        client_id=settings.youtube_oauth_client_id,
        client_secret=(
            settings.youtube_oauth_client_secret.get_secret_value()
            if settings.youtube_oauth_client_secret is not None
            else None
        ),
        max_retries=settings.live_max_retries,
    )


def create_dependencies(
    settings: Settings | None = None,
    provider: YouTubeProvider | None = None,
    repository: SQLiteRepository | None = None,
) -> ServerDependencies:
    """Build injectable app dependencies with an offline fixture provider by default."""
    resolved_settings = settings or load_settings()
    resolved_repository = (
        repository if repository is not None else SQLiteRepository(resolved_settings.db_path)
    )
    resolved_provider = (
        provider if provider is not None else _configured_provider(resolved_settings)
    )
    quota_guard = QuotaGuard(
        resolved_repository,
        daily_quota_budget=resolved_settings.daily_quota_budget,
        soft_warning_threshold=resolved_settings.soft_warning_threshold_units,
        max_search_pages=resolved_settings.max_search_pages,
    )
    sanitizer = MetadataSanitizer()
    similarity = SimilarityService(
        provider=resolved_provider,
        quota_guard=quota_guard,
        repo=resolved_repository,
        sanitizer=sanitizer,
    )
    return ServerDependencies(
        settings=resolved_settings,
        repository=resolved_repository,
        provider=resolved_provider,
        quota_guard=quota_guard,
        similarity=similarity,
        recommendations=RecommendationService(
            provider=resolved_provider,
            quota_guard=quota_guard,
            repo=resolved_repository,
            similarity=similarity,
            sanitizer=sanitizer,
        ),
        analytics=AnalyticsService(
            provider=resolved_provider,
            quota_guard=quota_guard,
            repo=resolved_repository,
            sanitizer=sanitizer,
        ),
        playlists=PlaylistService(
            provider=resolved_provider,
            quota_guard=quota_guard,
            repo=resolved_repository,
            sanitizer=sanitizer,
        ),
    )


def _register_tools(server: FastMCP, services: ServerDependencies) -> None:
    """Register all FR-1..FR-5 tools with Pydantic-validated arguments and outputs."""

    @server.tool()
    def find_similar_videos(
        video_ref: VideoRef,
        limit: VideoLimit = 10,
    ) -> SimilarVideosResponse | ToolErrorPayload:
        """Find ranked videos similar to a YouTube video URL or ID (`FR-1`)."""
        def execute() -> SimilarVideosResponse:
            args = SimilarVideosInput.model_validate(
                {"video_ref": video_ref, "limit": limit}
            )
            return services.similarity.find_similar_videos(args.video_ref, args.limit)

        return _map_tool_errors("find_similar_videos", execute)

    @server.tool()
    def find_similar_channels(
        channel_ref: ChannelRef,
        limit: ChannelLimit = 10,
    ) -> SimilarChannelsResponse | ToolErrorPayload:
        """Find ranked channels similar to a YouTube channel URL, handle, or ID (`FR-2`)."""
        def execute() -> SimilarChannelsResponse:
            args = SimilarChannelsInput.model_validate(
                {"channel_ref": channel_ref, "limit": limit}
            )
            return services.similarity.find_similar_channels(args.channel_ref, args.limit)

        return _map_tool_errors("find_similar_channels", execute)

    @server.tool()
    def get_recommendations(
        limit: VideoLimit = 10,
        exclude_known_videos: Literal[True] = True,
    ) -> RecommendationsResponse | ToolErrorPayload:
        """Recommend unseen videos from the authorized user's library (`FR-3`)."""
        def execute() -> RecommendationsResponse:
            args = RecommendationsInput.model_validate(
                {"limit": limit, "exclude_known_videos": exclude_known_videos}
            )
            return services.recommendations.recommend_for_user(args.limit)

        return _map_tool_errors("get_recommendations", execute)

    @server.tool()
    def analyze_user_engagement(
        period_days: PeriodDays = 30,
        compare_previous_period: bool = True,
    ) -> EngagementReport | ToolErrorPayload:
        """Analyze library engagement, duration preferences, and trends (`FR-4`)."""
        def execute() -> EngagementReport:
            args = EngagementInput.model_validate(
                {
                    "period_days": period_days,
                    "compare_previous_period": compare_previous_period,
                }
            )
            return services.analytics.analyze_engagement(
                period_days=args.period_days,
                compare_previous=args.compare_previous_period,
            )

        return _map_tool_errors("analyze_user_engagement", execute)

    @server.tool()
    def propose_playlist(
        topic: Topic,
        max_total_duration_minutes: PlaylistTotalMinutes,
        max_video_duration_minutes: PlaylistVideoMinutes | None = None,
        language: LanguageCode | None = None,
    ) -> PlaylistProposalResponse | ToolErrorPayload:
        """Propose a constrained playlist without writing to YouTube (`FR-5`, Phase 1)."""
        def execute() -> PlaylistProposalResponse:
            args = ProposePlaylistInput.model_validate(
                {
                    "topic": topic,
                    "max_total_duration_minutes": max_total_duration_minutes,
                    "max_video_duration_minutes": max_video_duration_minutes,
                    "language": language,
                }
            )
            request = PlaylistProposalRequest.model_validate(args.model_dump())
            return services.playlists.propose_playlist(request)

        return _map_tool_errors("propose_playlist", execute)

    @server.tool()
    def confirm_playlist(
        confirmation_token: ConfirmationToken,
        playlist_title: PlaylistTitle,
        user_confirmed: bool = False,
        playlist_description: PlaylistDescription = "",
        privacy_status: Literal["private", "unlisted", "public"] = "private",
    ) -> PlaylistCreatedResponse | ToolErrorPayload:
        """Create a proposed playlist only after explicit user confirmation (`FR-5`, Phase 2)."""
        def execute() -> PlaylistCreatedResponse:
            if user_confirmed is not True:
                raise ConfirmationRequiredError(
                    "Explicit user_confirmed=True is required before creating a YouTube playlist."
                )
            args = ConfirmPlaylistInput.model_validate(
                {
                    "confirmation_token": confirmation_token,
                    "user_confirmed": user_confirmed,
                    "playlist_title": playlist_title,
                    "playlist_description": playlist_description,
                    "privacy_status": privacy_status,
                }
            )
            return services.playlists.confirm_playlist(
                confirmation_token=args.confirmation_token,
                user_confirmed=args.user_confirmed,
                playlist_title=args.playlist_title,
                playlist_description=args.playlist_description,
                privacy_status=args.privacy_status,
            )

        return _map_tool_errors("confirm_playlist", execute)


def _create_fastapi_app(services: ServerDependencies) -> FastAPI:
    """Create health/OpenAPI HTTP routes around an already-configured MCP server."""

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(services.settings.log_level)
        services.repository.initialize_schema()
        logger.info("Initialized SQLite WAL database at %s", services.repository.db_path)
        async with fastapi_app.state.mcp.session_manager.run():
            yield

    fastapi_app = FastAPI(
        title="YouTube Video Intelligence MCP Server",
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    fastapi_app.state.settings = services.settings
    fastapi_app.state.provider = services.provider
    fastapi_app.state.repository = services.repository
    fastapi_app.state.quota_guard = services.quota_guard
    fastapi_app.state.services = services
    fastapi_app.state.mcp = FastMCP(SERVICE_NAME)
    fastapi_app.state.mcp.settings.streamable_http_path = "/"
    _register_tools(fastapi_app.state.mcp, services)

    @fastapi_app.get(
        "/api/v1/health",
        response_model=HealthResponse,
        tags=["health"],
        summary="Read-only server, SQLite WAL, and daily quota health check",
    )
    def health(request: Request) -> HealthResponse | JSONResponse:
        active_settings: Settings = request.app.state.settings
        repository: SQLiteRepository = request.app.state.repository
        try:
            try:
                wal_status = check_wal_health(
                    daily_quota_budget=active_settings.daily_quota_budget,
                    db_path=repository.db_path,
                )
            except sqlite3.OperationalError as exc:
                if "no such table" not in str(exc).lower():
                    raise
                repository.initialize_schema()
                wal_status = check_wal_health(
                    daily_quota_budget=active_settings.daily_quota_budget,
                    db_path=repository.db_path,
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

    fastapi_app.mount("/mcp", fastapi_app.state.mcp.streamable_http_app())
    return fastapi_app


def create_app(
    settings: Settings | None = None,
    provider: YouTubeProvider | None = None,
    repository: SQLiteRepository | None = None,
) -> FastAPI:
    """Create the injectable FastAPI and FastMCP application."""
    return _create_fastapi_app(create_dependencies(settings, provider, repository))


_default_dependencies = create_dependencies()
mcp = FastMCP(SERVICE_NAME)
_register_tools(mcp, _default_dependencies)
app = _create_fastapi_app(_default_dependencies)


def main() -> None:
    """Run the MCP server over `stdio` transport with `stderr`-only logging."""
    configure_logging(_default_dependencies.settings.log_level)
    _default_dependencies.repository.initialize_schema()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
