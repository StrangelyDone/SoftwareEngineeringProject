"""Offline `FixtureMockProvider` stub implementing `YouTubeProvider` (`TQ-5`, `ADR-003`).

Operates completely offline with zero network calls or `googleapiclient` imports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from youtube_mcp.providers.base import (
    ChannelMetadata,
    CreatedPlaylist,
    InvalidVideoIdentifierError,
    OAuthReauthorizationRequiredError,
    PlaylistItemResult,
    PlaylistSummary,
    QuotaBudgetExceededError,
    SearchPage,
    VideoMetadata,
    VideoUnavailableError,
    YouTubeProvider,
    YouTubeSignupRequiredError,
)

_FAULT_MAP: dict[str, type[Exception]] = {
    "INVALID_IDENTIFIER": InvalidVideoIdentifierError,
    "VIDEO_UNAVAILABLE": VideoUnavailableError,
    "QUOTA_BUDGET_EXCEEDED": QuotaBudgetExceededError,
    "OAUTH_REAUTH_REQUIRED": OAuthReauthorizationRequiredError,
    "YOUTUBE_SIGNUP_REQUIRED": YouTubeSignupRequiredError,
    "quotaExceeded": QuotaBudgetExceededError,
    "youtubeSignupRequired": YouTubeSignupRequiredError,
    "invalid_grant": OAuthReauthorizationRequiredError,
    "videoNotFound": VideoUnavailableError,
}

_DEFAULT_VIDEOS: dict[str, VideoMetadata] = {
    "dQw4w9WgXcQ": VideoMetadata(
        video_id="dQw4w9WgXcQ",
        title="Sample Offline Architecture Overview",
        description="Deterministic offline fixture video for Stage 2 scaffolding.",
        channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
        channel_title="Sample Channel",
        tags=["python", "mcp", "architecture"],
        category_id="28",
        duration_iso8601="PT10M15S",
        duration_seconds=615,
        default_language="en",
        default_audio_language="en",
    )
}

_DEFAULT_CHANNELS: dict[str, ChannelMetadata] = {
    "UC_x5XG1OV2P6uZZ5FSM9Ttw": ChannelMetadata(
        channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
        title="Sample Channel",
        description="Deterministic offline fixture channel for Stage 2 scaffolding.",
        handle="@samplechannel",
        topics=["Technology", "Software Engineering"],
        uploads_playlist_id="UU_x5XG1OV2P6uZZ5FSM9Ttw",
    )
}


class FixtureMockProvider(YouTubeProvider):
    """Offline mock provider backed by optional JSON fixtures or built-in stubs."""

    def __init__(
        self,
        fixtures_dir: Path | str | None = None,
        fault_mode: str | None = None,
    ) -> None:
        self.fixtures_dir: Path | None = (
            Path(fixtures_dir) if fixtures_dir is not None else None
        )
        self.fault_mode: str | None = fault_mode

    def inject_fault(self, error_type: str | None) -> None:
        """Configure deterministic fault injection for `TQ-4` negative tests."""
        self.fault_mode = error_type

    def _maybe_raise_fault(self) -> None:
        if self.fault_mode is None:
            return
        exc_cls = _FAULT_MAP.get(self.fault_mode)
        if exc_cls is not None:
            raise exc_cls(f"Injected offline mock fault: {self.fault_mode}")
        raise RuntimeError(f"Unknown injected fault mode: {self.fault_mode}")

    def _load_fixture(self, filename: str) -> Any | None:
        if self.fixtures_dir is None:
            return None
        candidate = self.fixtures_dir / filename
        if not candidate.is_file():
            return None
        return json.loads(candidate.read_text(encoding="utf-8"))

    def get_videos(self, video_ids: list[str]) -> list[VideoMetadata]:
        self._maybe_raise_fault()
        payload = self._load_fixture("videos.json")
        if isinstance(payload, list):
            by_id = {item["video_id"]: VideoMetadata(**item) for item in payload}
        else:
            by_id = _DEFAULT_VIDEOS
        return [by_id[vid] for vid in video_ids if vid in by_id]

    def get_channels(
        self,
        channel_ids: list[str] | None = None,
        handle: str | None = None,
    ) -> list[ChannelMetadata]:
        self._maybe_raise_fault()
        payload = self._load_fixture("channels.json")
        if isinstance(payload, list):
            channels = [ChannelMetadata(**item) for item in payload]
        else:
            channels = list(_DEFAULT_CHANNELS.values())

        if channel_ids:
            wanted = set(channel_ids)
            return [ch for ch in channels if ch.channel_id in wanted]
        if handle:
            normalized = handle if handle.startswith("@") else f"@{handle}"
            return [ch for ch in channels if ch.handle == normalized]
        return channels

    def search_videos(
        self,
        query: str,
        max_results: int = 25,
        page_token: str | None = None,
        language: str | None = None,
    ) -> SearchPage:
        self._maybe_raise_fault()
        _ = (query, page_token, language)
        video_ids = list(_DEFAULT_VIDEOS.keys())[:max_results]
        return SearchPage(video_ids=video_ids, next_page_token=None, total_results=len(video_ids))

    def get_user_likes(self, max_results: int = 50) -> list[VideoMetadata]:
        self._maybe_raise_fault()
        return list(_DEFAULT_VIDEOS.values())[:max_results]

    def get_user_subscriptions(self, max_results: int = 50) -> list[ChannelMetadata]:
        self._maybe_raise_fault()
        return list(_DEFAULT_CHANNELS.values())[:max_results]

    def get_user_playlists(self, max_results: int = 50) -> list[PlaylistSummary]:
        self._maybe_raise_fault()
        return [
            PlaylistSummary(
                playlist_id="PL_mock_offline_001",
                title="Offline Sample Playlist",
                description="Stub playlist for offline Stage 2 verification.",
                item_count=len(_DEFAULT_VIDEOS),
                privacy_status="private",
            )
        ][:max_results]

    def get_playlist_items(self, playlist_id: str, max_results: int = 50) -> list[str]:
        self._maybe_raise_fault()
        _ = playlist_id
        return list(_DEFAULT_VIDEOS.keys())[:max_results]

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ) -> CreatedPlaylist:
        self._maybe_raise_fault()
        _ = description
        playlist_id = "PL_mock_created_001"
        return CreatedPlaylist(
            playlist_id=playlist_id,
            title=title,
            privacy_status=privacy_status,
            playlist_url=f"https://www.youtube.com/playlist?list={playlist_id}",
        )

    def add_playlist_item(
        self,
        playlist_id: str,
        video_id: str,
    ) -> PlaylistItemResult:
        self._maybe_raise_fault()
        return PlaylistItemResult(
            playlist_id=playlist_id,
            video_id=video_id,
            playlist_item_id=f"PLI_mock_{video_id}",
        )
