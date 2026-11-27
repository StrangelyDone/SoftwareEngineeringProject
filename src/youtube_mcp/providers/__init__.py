"""External YouTube Data API v3 provider interfaces and adapters (`SE-6`, `ADR-003`)."""

from youtube_mcp.exceptions import (
    ConfirmationRequiredError,
    InvalidVideoIdentifierError,
    OAuthReauthorizationRequiredError,
    QuotaBudgetExceededError,
    VideoUnavailableError,
    YouTubeMCPError,
    YouTubeSignupRequiredError,
)
from youtube_mcp.models import (
    ChannelMetadata,
    CreatedPlaylist,
    PlaylistItemResult,
    PlaylistSummary,
    SearchPage,
    VideoMetadata,
)
from youtube_mcp.providers.base import YouTubeProvider
from youtube_mcp.providers.live import LiveYouTubeProvider
from youtube_mcp.providers.mock import FixtureMockProvider

__all__ = [
    "ChannelMetadata",
    "ConfirmationRequiredError",
    "CreatedPlaylist",
    "FixtureMockProvider",
    "InvalidVideoIdentifierError",
    "LiveYouTubeProvider",
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
