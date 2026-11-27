"""Abstract YouTubeProvider interface (`SE-6`, `ADR-003`)."""

from __future__ import annotations

from abc import ABC, abstractmethod

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

__all__ = [
    "ChannelMetadata",
    "ConfirmationRequiredError",
    "CreatedPlaylist",
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


class YouTubeProvider(ABC):
    """Abstract provider boundary isolating all YouTube Data API v3 & OAuth calls (`SE-6`)."""

    @abstractmethod
    def get_videos(self, video_ids: list[str]) -> list[VideoMetadata]:
        """Fetch metadata for up to 50 video IDs (`videos.list`)."""

    @abstractmethod
    def get_channels(
        self,
        channel_ids: list[str] | None = None,
        handle: str | None = None,
    ) -> list[ChannelMetadata]:
        """Fetch metadata for channel IDs or a `@handle` (`channels.list`)."""

    @abstractmethod
    def search_videos(
        self,
        query: str,
        max_results: int = 25,
        page_token: str | None = None,
        language: str | None = None,
    ) -> SearchPage:
        """Search public videos matching `query` (`search.list`)."""

    @abstractmethod
    def get_user_likes(self, max_results: int = 50) -> list[VideoMetadata]:
        """Fetch the authorized user's liked videos (`videos.list?myRating=like`)."""

    @abstractmethod
    def get_user_subscriptions(self, max_results: int = 50) -> list[ChannelMetadata]:
        """Fetch channels the authorized user subscribes to (`subscriptions.list`)."""

    @abstractmethod
    def get_user_playlists(self, max_results: int = 50) -> list[PlaylistSummary]:
        """Fetch playlists owned by the authorized user (`playlists.list`)."""

    @abstractmethod
    def get_playlist_items(self, playlist_id: str, max_results: int = 50) -> list[str]:
        """Fetch video IDs contained in a playlist (`playlistItems.list`)."""

    @abstractmethod
    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ) -> CreatedPlaylist:
        """Create a new playlist in the authorized user's account (`playlists.insert`)."""

    @abstractmethod
    def add_playlist_item(
        self,
        playlist_id: str,
        video_id: str,
    ) -> PlaylistItemResult:
        """Append a video to an existing playlist (`playlistItems.insert`)."""
