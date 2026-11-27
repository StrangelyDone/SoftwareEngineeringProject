"""Official YouTube Data API v3 live provider with OAuth and bounded backoff."""

from __future__ import annotations

import json
import logging
import os
import random
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self

import httpx

from youtube_mcp.exceptions import (
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

YOUTUBE_API_ROOT = "https://www.googleapis.com/youtube/v3"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class LiveYouTubeProvider(YouTubeProvider):
    """Official YouTube Data API v3 provider with OAuth refresh and retry handling."""

    def __init__(
        self,
        api_key: str | None = None,
        oauth_credentials_path: Path | str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.5,
        http_client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        jitter_fn: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        self.oauth_credentials_path = (
            Path(oauth_credentials_path)
            if oauth_credentials_path is not None
            else (
                Path(os.environ["YOUTUBE_OAUTH_TOKEN_PATH"])
                if os.getenv("YOUTUBE_OAUTH_TOKEN_PATH")
                else None
            )
        )
        self.client_id = client_id or os.getenv("YOUTUBE_OAUTH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET")
        self.max_retries = max(0, max_retries)
        self.base_backoff_seconds = max(0.0, base_backoff_seconds)
        self.sleep_fn = sleep_fn
        self.jitter_fn = jitter_fn
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client(timeout=30.0)
        self._oauth_data = self._load_oauth_data()

    def close(self) -> None:
        """Close owned HTTP resources."""
        if self._owns_client:
            self.http_client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _load_oauth_data(self) -> dict[str, Any]:
        if self.oauth_credentials_path is None:
            return {}
        if not self.oauth_credentials_path.is_file():
            return {}
        try:
            payload = json.loads(self.oauth_credentials_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _oauth_access_token(self) -> str | None:
        value = self._oauth_data.get("access_token")
        return value if isinstance(value, str) and value else None

    def _oauth_needs_refresh(self) -> bool:
        expires_at = self._oauth_data.get("expires_at")
        if not expires_at:
            return False
        try:
            expires_text = str(expires_at)
            if expires_text.endswith("Z"):
                expires_text = f"{expires_text[:-1]}+00:00"
            expiration = datetime.fromisoformat(expires_text)
        except ValueError:
            return True
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=UTC)
        return datetime.now(UTC) >= expiration - timedelta(seconds=60)

    def _ensure_oauth(self) -> str:
        if self._oauth_needs_refresh():
            self._refresh_oauth_token()
        access_token = self._oauth_access_token()
        if not access_token:
            raise OAuthReauthorizationRequiredError(
                "YouTube OAuth credentials are missing or cannot be refreshed."
            )
        return access_token

    def _refresh_oauth_token(self) -> None:
        refresh_token = self._oauth_data.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise OAuthReauthorizationRequiredError(
                "YouTube OAuth refresh credentials are missing."
            )
        if not self.client_id or not self.client_secret:
            raise OAuthReauthorizationRequiredError(
                "YouTube OAuth client credentials are missing."
            )

        response = self.http_client.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code != 200:
            payload = self._safe_json(response)
            reason = self._google_error_reason(payload)
            if response.status_code in {400, 401} or reason == "invalid_grant":
                raise OAuthReauthorizationRequiredError(
                    "YouTube OAuth authorization could not be renewed."
                )
            raise OAuthReauthorizationRequiredError(
                "YouTube OAuth authorization could not be renewed."
            )

        payload = self._safe_json(response)
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OAuthReauthorizationRequiredError(
                "YouTube OAuth authorization returned no access token."
            )

        expires_in = payload.get("expires_in")
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=float(expires_in))
            if isinstance(expires_in, (int, float))
            else datetime.now(UTC) + timedelta(hours=1)
        ).isoformat()

        refreshed = dict(self._oauth_data)
        refreshed["access_token"] = access_token
        refreshed["expires_at"] = expires_at
        if isinstance(payload.get("refresh_token"), str):
            refreshed["refresh_token"] = payload["refresh_token"]
        if isinstance(payload.get("scope"), str):
            refreshed["scopes"] = payload["scope"].split()

        self._oauth_data = refreshed
        self._persist_oauth_data(refreshed)

    def _persist_oauth_data(self, payload: dict[str, Any]) -> None:
        if self.oauth_credentials_path is None:
            return
        try:
            self.oauth_credentials_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.oauth_credentials_path.parent,
                prefix=".youtube-oauth-",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                json.dump(payload, temp_file)
                temp_path = Path(temp_file.name)
            os.replace(temp_path, self.oauth_credentials_path)
        except OSError as exc:
            raise OAuthReauthorizationRequiredError(
                "The refreshed YouTube OAuth token could not be stored safely."
            ) from exc

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _google_error_reason(payload: dict[str, Any]) -> str | None:
        error = payload.get("error")
        if isinstance(error, dict):
            for candidate in error.get("errors", []):
                if isinstance(candidate, dict) and candidate.get("reason"):
                    return str(candidate["reason"])
        if isinstance(error, dict) and error.get("status"):
            return str(error["status"])
        if isinstance(error, str):
            return error
        if isinstance(payload, dict) and payload.get("error"):
            value = payload["error"]
            if isinstance(value, dict) and value.get("reason"):
                return str(value["reason"])
        return None

    def _map_error_response(self, response: httpx.Response) -> YouTubeMCPError:
        payload = self._safe_json(response)
        reason = self._google_error_reason(payload)
        if response.status_code in {500, 502, 503, 504}:
            return YouTubeMCPError(
                "The YouTube API is temporarily unavailable.",
                "Retry the request later.",
            )
        message = ""
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message = error["message"]

        if reason in {"quotaExceeded", "dailyLimitExceeded"}:
            return QuotaBudgetExceededError()
        if reason == "youtubeSignupRequired":
            return YouTubeSignupRequiredError()
        if reason in {"videoNotFound", "playlistNotFound", "channelNotFound"}:
            return VideoUnavailableError()
        if reason in {"invalid_grant", "unauthorized"}:
            return OAuthReauthorizationRequiredError()
        if response.status_code == 401:
            return OAuthReauthorizationRequiredError()
        if response.status_code == 403:
            return QuotaBudgetExceededError(
                "YouTube rejected the request for quota or authorization."
            )
        if response.status_code == 429:
            return QuotaBudgetExceededError(
                "YouTube rate limited the request after bounded retries."
            )
        return YouTubeMCPError(
            message or "The YouTube API returned an unsuccessful response.",
            "Retry the request or verify the provider configuration.",
        )

    def _backoff_delay(self, attempt: int, response: httpx.Response | None) -> float:
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 30.0)
            except ValueError:
                pass
        exponential = self.base_backoff_seconds * (2**attempt)
        jitter = self.jitter_fn(0.0, min(exponential, 1.0))
        return min(exponential + jitter, 30.0)

    def _request_with_backoff(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        oauth: bool = False,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = dict(headers or {})

        if oauth:
            request_headers["Authorization"] = f"Bearer {self._ensure_oauth()}"
        elif self.api_key:
            params = dict(params or {})
            params["key"] = self.api_key

        url = endpoint if endpoint.startswith("http") else f"{YOUTUBE_API_ROOT}/{endpoint}"
        oauth_refresh_attempted = False

        for attempt in range(self.max_retries + 1):
            try:
                response = self.http_client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=request_headers,
                )
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise YouTubeMCPError(
                        "The YouTube API transport could not complete the request.",
                        "Retry the request when the network is available.",
                    )
                self.sleep_fn(self._backoff_delay(attempt, None))
                continue

            if response.status_code == 401 and oauth and not oauth_refresh_attempted:
                oauth_refresh_attempted = True
                self._refresh_oauth_token()
                request_headers["Authorization"] = f"Bearer {self._ensure_oauth()}"
                continue

            if response.status_code == 429 or response.status_code in {500, 502, 503, 504}:
                if attempt >= self.max_retries:
                    raise self._map_error_response(response)
                self.sleep_fn(self._backoff_delay(attempt, response))
                continue

            if response.is_error:
                raise self._map_error_response(response)

            payload = self._safe_json(response)
            if not payload:
                return {}
            return payload

        raise YouTubeMCPError(
            "The YouTube API request exhausted bounded retries.",
            "Retry the request later.",
        )

    @staticmethod
    def _normalize_duration(content_details: dict[str, Any] | None) -> str | None:
        if not isinstance(content_details, dict):
            return None
        value = content_details.get("duration")
        return value if isinstance(value, str) else None

    @staticmethod
    def _parse_duration_seconds(duration_iso: str | None) -> int | None:
        if not duration_iso:
            return None
        import re

        match = re.fullmatch(
            r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
            duration_iso,
        )
        if not match:
            return None
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = float(match.group(3) or 0)
        return int(hours * 3600 + minutes * 60 + seconds)

    def _video_from_item(self, item: dict[str, Any]) -> VideoMetadata:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        statistics = item.get("statistics", {})
        topic_details = item.get("topicDetails", {})
        if not isinstance(snippet, dict):
            snippet = {}
        if not isinstance(content, dict):
            content = {}
        if not isinstance(statistics, dict):
            statistics = {}
        if not isinstance(topic_details, dict):
            topic_details = {}

        tags = snippet.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        duration_iso = self._normalize_duration(content)
        category_id = snippet.get("categoryId")

        def optional_int(value: Any) -> int | None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return VideoMetadata(
            video_id=str(item.get("id", "")),
            title=str(snippet.get("title", "")),
            description=str(snippet.get("description", "")),
            channel_id=str(snippet.get("channelId", "")),
            channel_title=str(snippet.get("channelTitle", "")),
            tags=[str(tag) for tag in tags],
            category_id=str(category_id) if category_id is not None else None,
            duration_iso=duration_iso,
            duration_seconds=self._parse_duration_seconds(duration_iso),
            default_language=snippet.get("defaultLanguage"),
            default_audio_language=snippet.get("defaultAudioLanguage"),
            published_at=snippet.get("publishedAt"),
            view_count=optional_int(statistics.get("viewCount")),
            like_count=optional_int(statistics.get("likeCount")),
        )

    def get_videos(self, video_ids: list[str]) -> list[VideoMetadata]:
        if not video_ids:
            return []

        videos: list[VideoMetadata] = []
        for start in range(0, len(video_ids), 50):
            chunk = video_ids[start : start + 50]
            payload = self._request_with_backoff(
                "GET",
                "videos",
                params={
                    "part": "snippet,contentDetails,statistics,topicDetails",
                    "id": ",".join(chunk),
                },
            )
            items = payload.get("items", [])
            if not isinstance(items, list):
                items = []
            videos.extend(
                self._video_from_item(item)
                for item in items
                if isinstance(item, dict)
            )
        if not videos:
            raise VideoUnavailableError()
        return videos

    def _channel_from_item(self, item: dict[str, Any]) -> ChannelMetadata:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        statistics = item.get("statistics", {})
        topic_details = item.get("topicDetails", {})
        branding = item.get("brandingSettings", {})
        if not isinstance(snippet, dict):
            snippet = {}
        if not isinstance(content, dict):
            content = {}
        if not isinstance(statistics, dict):
            statistics = {}
        if not isinstance(topic_details, dict):
            topic_details = {}
        if not isinstance(branding, dict):
            branding = {}

        related = content.get("relatedPlaylists", {})
        uploads = related.get("uploads") if isinstance(related, dict) else None
        topics = topic_details.get("topicCategories", [])
        if not isinstance(topics, list):
            topics = []
        channel_branding = branding.get("channel", {})
        keywords = channel_branding.get("keywords", "") if isinstance(channel_branding, dict) else ""
        keyword_list = (
            [part.strip().strip('"') for part in str(keywords).split() if part.strip()]
            if keywords
            else []
        )

        def optional_int(value: Any) -> int | None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return ChannelMetadata(
            channel_id=str(item.get("id", "")),
            title=str(snippet.get("title", "")),
            description=str(snippet.get("description", "")),
            handle=snippet.get("customUrl"),
            keywords=keyword_list,
            topic_categories=[str(topic) for topic in topics],
            uploads_playlist_id=uploads if isinstance(uploads, str) else None,
            subscriber_count=optional_int(statistics.get("subscriberCount")),
            video_count=optional_int(statistics.get("videoCount")),
            country=snippet.get("country"),
        )

    def get_channels(
        self,
        channel_ids: list[str] | None = None,
        handle: str | None = None,
    ) -> list[ChannelMetadata]:
        params: dict[str, Any] = {
            "part": "snippet,contentDetails,statistics,topicDetails,brandingSettings"
        }
        if channel_ids:
            params["id"] = ",".join(channel_ids)
        elif handle:
            normalized = handle.lstrip("@")
            params["forHandle"] = normalized
        else:
            raise VideoUnavailableError("No channel ID or handle was supplied.")

        payload = self._request_with_backoff("GET", "channels", params=params)
        items = payload.get("items", [])
        if not isinstance(items, list) or not items:
            raise VideoUnavailableError()
        channels = [
            self._channel_from_item(item)
            for item in items
            if isinstance(item, dict)
        ]
        if not channels:
            raise VideoUnavailableError()
        return channels

    def search_videos(
        self,
        query: str,
        max_results: int = 25,
        page_token: str | None = None,
        language: str | None = None,
    ) -> SearchPage:
        params: dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": max(1, min(max_results, 50)),
        }
        if page_token:
            params["pageToken"] = page_token
        if language:
            params["relevanceLanguage"] = language

        payload = self._request_with_backoff("GET", "search", params=params)
        items = payload.get("items", [])
        video_ids: list[str] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id", {})
                if isinstance(item_id, dict) and isinstance(item_id.get("videoId"), str):
                    video_ids.append(item_id["videoId"])

        page_info = payload.get("pageInfo", {})
        total_results = (
            page_info.get("totalResults")
            if isinstance(page_info, dict)
            else payload.get("pageInfo")
        )
        try:
            total = int(total_results) if total_results is not None else None
        except (TypeError, ValueError):
            total = None
        next_token = payload.get("nextPageToken")

        return SearchPage(
            video_ids=video_ids,
            next_page_token=next_token if isinstance(next_token, str) else None,
            total_results=total,
        )

    def get_user_likes(self, max_results: int = 50) -> list[VideoMetadata]:
        payload = self._request_with_backoff(
            "GET",
            "videos",
            params={
                "part": "snippet,contentDetails,statistics,topicDetails",
                "myRating": "like",
                "maxResults": max(1, min(max_results, 50)),
            },
            oauth=True,
        )
        items = payload.get("items", [])
        if not isinstance(items, list):
            return []
        return [
            self._video_from_item(item)
            for item in items
            if isinstance(item, dict)
        ]

    def get_user_subscriptions(self, max_results: int = 50) -> list[ChannelMetadata]:
        payload = self._request_with_backoff(
            "GET",
            "subscriptions",
            params={
                "mine": "true",
                "part": "snippet",
                "maxResults": max(1, min(max_results, 50)),
            },
            oauth=True,
        )
        items = payload.get("items", [])
        channel_ids: list[str] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                snippet = item.get("snippet", {})
                if not isinstance(snippet, dict):
                    continue
                resource = snippet.get("resourceId", {})
                if isinstance(resource, dict) and isinstance(resource.get("channelId"), str):
                    channel_ids.append(resource["channelId"])
        if not channel_ids:
            return []
        return self.get_channels(channel_ids=channel_ids)

    def get_user_playlists(self, max_results: int = 50) -> list[PlaylistSummary]:
        payload = self._request_with_backoff(
            "GET",
            "playlists",
            params={
                "mine": "true",
                "part": "snippet,contentDetails,status",
                "maxResults": max(1, min(max_results, 50)),
            },
            oauth=True,
        )
        items = payload.get("items", [])
        playlists: list[PlaylistSummary] = []
        if not isinstance(items, list):
            return playlists
        for item in items:
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            status = item.get("status", {})
            if not isinstance(snippet, dict):
                snippet = {}
            if not isinstance(content, dict):
                content = {}
            if not isinstance(status, dict):
                status = {}
            try:
                item_count = int(content.get("itemCount", 0))
            except (TypeError, ValueError):
                item_count = 0
            playlists.append(
                PlaylistSummary(
                    playlist_id=str(item.get("id", "")),
                    title=str(snippet.get("title", "")),
                    description=str(snippet.get("description", "")),
                    item_count=item_count,
                    privacy_status=str(status.get("privacyStatus", "private")),
                )
            )
        return playlists

    def get_playlist_items(self, playlist_id: str, max_results: int = 50) -> list[str]:
        payload = self._request_with_backoff(
            "GET",
            "playlistItems",
            params={
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": max(1, min(max_results, 50)),
            },
        )
        items = payload.get("items", [])
        video_ids: list[str] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                content = item.get("contentDetails", {})
                if isinstance(content, dict) and isinstance(content.get("videoId"), str):
                    video_ids.append(content["videoId"])
        return video_ids

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ) -> CreatedPlaylist:
        payload = self._request_with_backoff(
            "POST",
            "playlists",
            params={"part": "snippet,status"},
            json_body={
                "snippet": {"title": title, "description": description},
                "status": {"privacyStatus": privacy_status},
            },
            oauth=True,
        )
        playlist_id = str(payload.get("id", ""))
        snippet = payload.get("snippet", {})
        status = payload.get("status", {})
        if not isinstance(snippet, dict):
            snippet = {}
        if not isinstance(status, dict):
            status = {}
        if not playlist_id:
            raise YouTubeMCPError(
                "YouTube did not return a created playlist ID.",
                "Verify playlist creation configuration and retry.",
            )
        return CreatedPlaylist(
            playlist_id=playlist_id,
            title=str(snippet.get("title", title)),
            url=f"https://www.youtube.com/playlist?list={playlist_id}",
            privacy_status=str(status.get("privacyStatus", privacy_status)),
        )

    def add_playlist_item(
        self,
        playlist_id: str,
        video_id: str,
    ) -> PlaylistItemResult:
        payload = self._request_with_backoff(
            "POST",
            "playlistItems",
            params={"part": "snippet"},
            json_body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
            oauth=True,
        )
        item_id = str(payload.get("id", ""))
        snippet = payload.get("snippet", {})
        position = 0
        if isinstance(snippet, dict):
            try:
                position = int(snippet.get("position", 0))
            except (TypeError, ValueError):
                position = 0
        if not item_id:
            raise YouTubeMCPError(
                "YouTube did not return a playlist item ID.",
                "Verify the playlist and video IDs and retry.",
            )
        return PlaylistItemResult(
            playlist_id=playlist_id,
            video_id=video_id,
            playlist_item_id=item_id,
            position=position,
        )
