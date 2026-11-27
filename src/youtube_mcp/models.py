"""Pydantic v2 domain models shared by YouTube provider implementations."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class VideoMetadata(BaseModel):
    """Normalized YouTube video metadata."""

    model_config = ConfigDict(populate_by_name=True)

    video_id: str
    title: str
    description: str = ""
    channel_id: str = ""
    channel_title: str = ""
    tags: list[str] = Field(default_factory=list)
    category_id: str | None = None
    duration_iso: str | None = Field(
        default=None,
        validation_alias=AliasChoices("duration_iso", "duration_iso8601"),
        serialization_alias="duration_iso",
    )
    duration_seconds: int | None = None
    default_language: str | None = None
    default_audio_language: str | None = None
    published_at: str | None = None
    view_count: int | None = None
    like_count: int | None = None

    @property
    def duration_iso8601(self) -> str | None:
        """Compatibility name used by the existing scaffold and fixtures."""
        return self.duration_iso


class ChannelMetadata(BaseModel):
    """Normalized YouTube channel metadata."""

    model_config = ConfigDict(populate_by_name=True)

    channel_id: str
    title: str
    description: str = ""
    handle: str | None = None
    keywords: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("keywords", "topics"),
    )
    topic_categories: list[str] = Field(default_factory=list)
    uploads_playlist_id: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    country: str | None = None

    @property
    def topics(self) -> list[str]:
        """Compatibility name used by the existing scaffold."""
        return self.keywords


class SearchPage(BaseModel):
    """Paginated public video search results."""

    model_config = ConfigDict(populate_by_name=True)

    video_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("video_ids", "items"),
    )
    next_page_token: str | None = None
    total_results: int | None = None

    @property
    def items(self) -> list[str]:
        """Compatibility name for callers that use `items`."""
        return self.video_ids


class PlaylistSummary(BaseModel):
    """Summary of an existing user playlist."""

    playlist_id: str
    title: str
    description: str = ""
    item_count: int = 0
    privacy_status: str = "private"


class CreatedPlaylist(BaseModel):
    """Result of creating a playlist."""

    model_config = ConfigDict(populate_by_name=True)

    playlist_id: str
    title: str
    url: str = Field(
        validation_alias=AliasChoices("url", "playlist_url"),
        serialization_alias="url",
    )
    privacy_status: str = "private"

    @property
    def playlist_url(self) -> str:
        """Compatibility name used by the existing scaffold."""
        return self.url


class PlaylistItemResult(BaseModel):
    """Result of appending a video to a playlist."""

    playlist_id: str
    video_id: str
    playlist_item_id: str
    position: int = 0


__all__ = [
    "ChannelMetadata",
    "CreatedPlaylist",
    "PlaylistItemResult",
    "PlaylistSummary",
    "SearchPage",
    "VideoMetadata",
]
