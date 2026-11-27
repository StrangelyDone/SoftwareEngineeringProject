"""External YouTube Data API v3 provider interfaces and adapters (`SE-6`, `ADR-003`)."""

from youtube_mcp.providers.base import (
    ChannelMetadata,
    ConfirmationRequiredError,
    CreatedPlaylist,
    InvalidVideoIdentifierError,
    OAuthReauthorizationRequiredError,
    PlaylistItemResult,
    PlaylistSummary,
    QuotaBudgetExceededError,
    SearchPage,
    VideoMetadata,
    VideoUnavailableError,
    YouTubeMCPError,
    YouTubeProvider,
    YouTubeSignupRequiredError,
)
from youtube_mcp.providers.mock import FixtureMockProvider

__all__ = [
    "ChannelMetadata",
    "ConfirmationRequiredError",
    "CreatedPlaylist",
    "FixtureMockProvider",
    "InvalidVideoIdentifierError",
    "OAuthReauthorizationRequiredError",
    "PlaylistItemResult",
    "PlaylistSummary",
    "QuotaBudgetExceededError",
    "SearchPage",
    "VideoMetadata",
    "VideoUnavailableError",
    "YouTubeMCPError",
    "YouTubeProvider",
    "YouTubeSignupRequiredError",
]
