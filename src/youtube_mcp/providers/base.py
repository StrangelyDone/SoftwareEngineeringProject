"""Abstract YouTubeProvider interface, domain models, and exception hierarchy (`SE-6`, `ADR-003`).

This module must never import `googleapiclient` or execute live network calls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class YouTubeMCPError(Exception):
    """Base domain exception mapped to structured MCP error payloads."""

    error_code: str = "YOUTUBE_MCP_ERROR"
    default_remediation: str = "Verify your request parameters and try again."

    def __init__(self, message: str, remediation: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.remediation = remediation or self.default_remediation

    def to_payload(self) -> dict[str, str]:
        """Return a safe structured error payload without stack traces or secrets."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "remediation": self.remediation,
        }


class InvalidVideoIdentifierError(YouTubeMCPError):
    """Raised when a video URL, channel URL, `@handle`, or ID fails validation (`TQ-4`)."""

    error_code = "INVALID_IDENTIFIER"
    default_remediation = (
        "Provide a valid YouTube URL, 11-char video ID, @handle, or UC... channel ID."
    )


class VideoUnavailableError(YouTubeMCPError):
    """Raised when a video or channel is private, deleted, or nonexistent (`TQ-4`)."""

    error_code = "VIDEO_UNAVAILABLE"
    default_remediation = (
        "Verify the video is public/accessible and retry with another ID."
    )


class QuotaBudgetExceededError(YouTubeMCPError):
    """Raised on TQ-6 pre-flight rejection or upstream `quotaExceeded`."""

    error_code = "QUOTA_BUDGET_EXCEEDED"
    default_remediation = (
        "Wait for UTC midnight quota reset, reduce result scope, or rely on cached entries."
    )


class ConfirmationRequiredError(YouTubeMCPError):
    """Raised when `FR-5` confirmation is missing, invalid, expired, or replayed."""

    error_code = "CONFIRMATION_REQUIRED"
    default_remediation = (
        "Re-run propose_playlist and obtain explicit human confirmation before "
        "calling confirm_playlist."
    )


class OAuthReauthorizationRequiredError(YouTubeMCPError):
    """Raised when OAuth credentials are missing or the 7-day Testing token expired."""

    error_code = "OAUTH_REAUTH_REQUIRED"
    default_remediation = (
        "Re-run the local OAuth 2.0 authorization flow to issue a fresh refresh token."
    )


class YouTubeSignupRequiredError(YouTubeMCPError):
    """Raised when the authenticated Google account has no YouTube channel."""

    error_code = "YOUTUBE_SIGNUP_REQUIRED"
    default_remediation = (
        "Create a YouTube channel on the authenticated Google account before creating playlists."
    )


class VideoMetadata(BaseModel):
    """Normalized YouTube video metadata returned by `YouTubeProvider`."""

    video_id: str
    title: str
    description: str = ""
    channel_id: str = ""
    channel_title: str = ""
    tags: list[str] = Field(default_factory=list)
    category_id: str | None = None
    duration_iso8601: str | None = None
    duration_seconds: int | None = None
    default_language: str | None = None
    default_audio_language: str | None = None
    published_at: str | None = None
    view_count: int | None = None
    like_count: int | None = None


class ChannelMetadata(BaseModel):
    """Normalized YouTube channel metadata returned by `YouTubeProvider`."""

    channel_id: str
    title: str
    description: str = ""
    handle: str | None = None
    topics: list[str] = Field(default_factory=list)
    uploads_playlist_id: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    country: str | None = None


class SearchPage(BaseModel):
    """Paginated `search.list` candidate video IDs."""

    video_ids: list[str] = Field(default_factory=list)
    next_page_token: str | None = None
    total_results: int | None = None


class PlaylistSummary(BaseModel):
    """Summary of an existing playlist in the authorized user's library."""

    playlist_id: str
    title: str
    description: str = ""
    item_count: int = 0
    privacy_status: str = "private"


class CreatedPlaylist(BaseModel):
    """Result of `playlists.insert`."""

    playlist_id: str
    title: str
    privacy_status: str = "private"
    playlist_url: str


class PlaylistItemResult(BaseModel):
    """Result of `playlistItems.insert`."""

    playlist_id: str
    video_id: str
    playlist_item_id: str


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
