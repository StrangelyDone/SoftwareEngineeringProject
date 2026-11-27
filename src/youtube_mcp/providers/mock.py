"""Deterministic offline FixtureMockProvider (`TQ-5`, `ADR-003`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from youtube_mcp.exceptions import (
    ConfirmationRequiredError,
    InvalidVideoIdentifierError,
    OAuthReauthorizationRequiredError,
    QuotaBudgetExceededError,
    VideoUnavailableError,
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

SUPPORTED_FAULTS: dict[str, type[Exception]] = {
    "video_unavailable": VideoUnavailableError,
    "quota_exceeded": QuotaBudgetExceededError,
    "youtube_signup_required": YouTubeSignupRequiredError,
    "oauth_reauth_required": OAuthReauthorizationRequiredError,
    "invalid_grant": OAuthReauthorizationRequiredError,
    "invalid_identifier": InvalidVideoIdentifierError,
    "confirmation_required": ConfirmationRequiredError,
}

_PRIVATE_VIDEO_IDS = {
    "PRIVATE_VIDEO",
    "vidPRIVATE001",
}


class FixtureMockProvider(YouTubeProvider):
    """Offline provider loaded from sanitized repository JSON fixtures."""

    def __init__(
        self,
        fixtures_dir: Path | str | None = None,
        fault_mode: str | None = None,
    ) -> None:
        if fixtures_dir is None:
            self.fixtures_dir = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
        else:
            self.fixtures_dir = Path(fixtures_dir)

        self._fault_mode: str | None = None
        self._created_playlists: dict[str, CreatedPlaylist] = {}
        self._created_playlist_items: dict[str, list[str]] = {}
        self._created_playlist_summaries: dict[str, PlaylistSummary] = {}
        self._playlist_counter = 0
        self._position_counter: dict[str, int] = {}

        self._videos = self._load_videos()
        self._channels = self._load_channels()
        self._library = self._load_json("user_library.json")
        self._error_payloads = self._load_json("error_payloads.json")

        if fault_mode is not None:
            self.inject_fault(fault_mode)

    def inject_fault(self, error_type: str | None) -> None:
        """Set, clear, or validate a deterministic provider fault."""
        if error_type is None:
            self._fault_mode = None
            return
        if error_type not in SUPPORTED_FAULTS:
            raise ValueError(f"Unknown fixture fault mode: {error_type}")
        self._fault_mode = error_type

    @property
    def fault_mode(self) -> str | None:
        """Backward-compatible access to the active fault mode."""
        return self._fault_mode

    @property
    def error_payloads(self) -> dict[str, Any]:
        """Return sanitized error payload fixtures."""
        return self._error_payloads

    def _maybe_raise_fault(self) -> None:
        if self._fault_mode is None:
            return
        exc_class = SUPPORTED_FAULTS[self._fault_mode]
        raise exc_class(f"Injected offline fixture fault: {self._fault_mode}")

    def _load_json(self, filename: str) -> dict[str, Any] | list[Any]:
        path = self.fixtures_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing fixture: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_videos(self) -> dict[str, VideoMetadata]:
        payload = self._load_json("videos.json")
        if not isinstance(payload, list):
            raise TypeError("videos.json must contain a JSON list")
        return {
            item["video_id"]: VideoMetadata.model_validate(item)
            for item in payload
            if isinstance(item, dict)
        }

    def _load_channels(self) -> dict[str, ChannelMetadata]:
        payload = self._load_json("channels.json")
        if not isinstance(payload, list):
            raise TypeError("channels.json must contain a JSON list")
        return {
            item["channel_id"]: ChannelMetadata.model_validate(item)
            for item in payload
            if isinstance(item, dict)
        }

    def get_videos(self, video_ids: list[str]) -> list[VideoMetadata]:
        self._maybe_raise_fault()
        if not video_ids:
            return []

        requested = set(video_ids)
        unavailable = requested & _PRIVATE_VIDEO_IDS
        if unavailable:
            raise VideoUnavailableError("A requested synthetic video is unavailable.")

        missing = requested - set(self._videos)
        if missing:
            raise VideoUnavailableError("One or more requested synthetic videos were not found.")
        return [self._videos[video_id] for video_id in video_ids if video_id in self._videos]

    def get_channels(
        self,
        channel_ids: list[str] | None = None,
        handle: str | None = None,
    ) -> list[ChannelMetadata]:
        self._maybe_raise_fault()
        candidates = list(self._channels.values())

        if channel_ids:
            wanted = set(channel_ids)
            candidates = [channel for channel in candidates if channel.channel_id in wanted]

        if handle:
            normalized = handle.lower()
            if not normalized.startswith("@"):
                normalized = f"@{normalized}"
            candidates = [
                channel
                for channel in candidates
                if channel.handle is not None
                and channel.handle.lower() == normalized
            ]

        if not candidates:
            raise VideoUnavailableError("No matching synthetic channel was found.")
        return candidates

    def search_videos(
        self,
        query: str,
        max_results: int = 25,
        page_token: str | None = None,
        language: str | None = None,
    ) -> SearchPage:
        self._maybe_raise_fault()
        max_results = max(1, min(max_results, 50))
        terms = [term.casefold() for term in query.strip().split() if term]

        matches: list[VideoMetadata] = []
        for video in self._videos.values():
            if language and video.default_language != language:
                continue
            searchable = " ".join(
                [
                    video.title,
                    video.description,
                    " ".join(video.tags),
                    video.channel_title,
                ]
            ).casefold()
            if not terms or all(term in searchable for term in terms):
                matches.append(video)

        try:
            start = int(page_token) if page_token else 0
        except ValueError:
            start = 0
        start = max(start, 0)
        end = start + max_results
        page_ids = [video.video_id for video in matches[start:end]]
        next_page_token = str(end) if end < len(matches) else None

        return SearchPage(
            video_ids=page_ids,
            next_page_token=next_page_token,
            total_results=len(matches),
        )

    def get_user_likes(self, max_results: int = 50) -> list[VideoMetadata]:
        self._maybe_raise_fault()
        if not isinstance(self._library, dict):
            raise TypeError("user_library.json must contain a JSON object")
        ids = self._library.get("liked_video_ids", [])
        return [self._videos[video_id] for video_id in ids[:max_results] if video_id in self._videos]

    def get_user_subscriptions(self, max_results: int = 50) -> list[ChannelMetadata]:
        self._maybe_raise_fault()
        if not isinstance(self._library, dict):
            raise TypeError("user_library.json must contain a JSON object")
        ids = self._library.get("subscribed_channel_ids", [])
        return [
            self._channels[channel_id]
            for channel_id in ids[:max_results]
            if channel_id in self._channels
        ]

    def get_user_playlists(self, max_results: int = 50) -> list[PlaylistSummary]:
        self._maybe_raise_fault()
        if not isinstance(self._library, dict):
            raise TypeError("user_library.json must contain a JSON object")
        playlists = [
            PlaylistSummary.model_validate(item)
            for item in self._library.get("playlists", [])
        ]
        playlists.extend(self._created_playlist_summaries.values())
        return playlists[:max_results]

    def get_playlist_items(self, playlist_id: str, max_results: int = 50) -> list[str]:
        self._maybe_raise_fault()
        if not isinstance(self._library, dict):
            raise TypeError("user_library.json must contain a JSON object")
        mappings = self._library.get("playlist_items", {})
        fixture_ids = mappings.get(playlist_id, []) if isinstance(mappings, dict) else []
        created_ids = self._created_playlist_items.get(playlist_id, [])
        return list(dict.fromkeys([*fixture_ids, *created_ids]))[:max_results]

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ) -> CreatedPlaylist:
        self._maybe_raise_fault()
        self._playlist_counter += 1
        playlist_id = f"PLmockcreated{self._playlist_counter:03d}"
        created = CreatedPlaylist(
            playlist_id=playlist_id,
            title=title,
            privacy_status=privacy_status,
            url=f"https://www.youtube.com/playlist?list={playlist_id}",
        )
        self._created_playlists[playlist_id] = created
        self._created_playlist_items[playlist_id] = []
        self._position_counter[playlist_id] = 0
        self._created_playlist_summaries[playlist_id] = PlaylistSummary(
            playlist_id=playlist_id,
            title=title,
            description=description,
            item_count=0,
            privacy_status=privacy_status,
        )
        return created

    def add_playlist_item(
        self,
        playlist_id: str,
        video_id: str,
    ) -> PlaylistItemResult:
        self._maybe_raise_fault()
        if video_id not in self._videos:
            raise VideoUnavailableError("The requested synthetic video is unavailable.")

        if playlist_id not in self._created_playlists:
            if not isinstance(self._library, dict):
                raise TypeError("user_library.json must contain a JSON object")
            mappings = self._library.get("playlist_items", {})
            if not isinstance(mappings, dict) or playlist_id not in mappings:
                raise VideoUnavailableError("The requested synthetic playlist was not found.")
            self._created_playlist_items.setdefault(playlist_id, [])
            self._position_counter.setdefault(playlist_id, len(mappings[playlist_id]))

        position = self._position_counter.get(playlist_id, 0)
        if video_id not in self._created_playlist_items[playlist_id]:
            self._created_playlist_items[playlist_id].append(video_id)
            position = len(self._created_playlist_items[playlist_id]) - 1
            self._position_counter[playlist_id] = position + 1

        if playlist_id in self._created_playlist_summaries:
            summary = self._created_playlist_summaries[playlist_id]
            self._created_playlist_summaries[playlist_id] = summary.model_copy(
                update={"item_count": len(self._created_playlist_items[playlist_id])}
            )

        return PlaylistItemResult(
            playlist_id=playlist_id,
            video_id=video_id,
            playlist_item_id=f"PLI_mock_{playlist_id}_{video_id}",
            position=position,
        )
