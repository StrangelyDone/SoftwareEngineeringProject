"""Offline mock/live provider contract parity and resilience tests."""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

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
from youtube_mcp.providers.live import LiveYouTubeProvider
from youtube_mcp.providers.mock import FixtureMockProvider

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FixtureWireTransport:
    """Translate sanitized fixtures into official YouTube Data API wire payloads."""

    def __init__(self) -> None:
        self.videos = _load_json("videos.json")
        self.channels = _load_json("channels.json")
        self.library = _load_json("user_library.json")
        self.created_playlists: dict[str, dict[str, Any]] = {}
        self.created_items: dict[str, list[str]] = {}
        self.counter = 0

    def _video_wire(self, video: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "youtube#video",
            "id": video["video_id"],
            "snippet": {
                "title": video["title"],
                "description": video.get("description", ""),
                "channelId": video.get("channel_id", ""),
                "channelTitle": video.get("channel_title", ""),
                "categoryId": video.get("category_id"),
                "tags": video.get("tags", []),
                "publishedAt": video.get("published_at"),
                "defaultLanguage": video.get("default_language"),
                "defaultAudioLanguage": video.get("default_audio_language"),
            },
            "contentDetails": {
                "duration": video.get("duration_iso"),
            } if video.get("duration_iso") else {},
            "statistics": {
                "viewCount": str(video["view_count"]) if video.get("view_count") is not None else None,
                "likeCount": str(video["like_count"]) if video.get("like_count") is not None else None,
            },
            "topicDetails": {},
        }

    def _channel_wire(self, channel: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "youtube#channel",
            "id": channel["channel_id"],
            "snippet": {
                "title": channel["title"],
                "description": channel.get("description", ""),
                "customUrl": channel.get("handle"),
                "country": channel.get("country"),
            },
            "contentDetails": {
                "relatedPlaylists": {
                    "uploads": channel.get("uploads_playlist_id"),
                }
            },
            "statistics": {
                "subscriberCount": str(channel["subscriber_count"])
                if channel.get("subscriber_count") is not None
                else None,
                "videoCount": str(channel["video_count"])
                if channel.get("video_count") is not None
                else None,
            },
            "topicDetails": {
                "topicCategories": channel.get("topic_categories", [])
            },
            "brandingSettings": {
                "channel": {
                    "keywords": " ".join(channel.get("keywords", [])),
                }
            },
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith("/videos"):
            if request.url.params.get("myRating") == "like":
                ids = self.library["liked_video_ids"]
                max_results = int(request.url.params.get("maxResults", 50))
                items = [
                    self._video_wire(video)
                    for video in self.videos
                    if video["video_id"] in ids
                ][:max_results]
                return httpx.Response(200, json={"items": items})
            ids = request.url.params.get("id", "").split(",")
            items = [
                self._video_wire(video)
                for video in self.videos
                if video["video_id"] in ids
            ]
            return httpx.Response(200, json={"items": items})

        if path.endswith("/channels"):
            channel_ids = request.url.params.get("id")
            handle = request.url.params.get("forHandle")
            if channel_ids:
                wanted = set(channel_ids.split(","))
                matches = [
                    channel for channel in self.channels
                    if channel["channel_id"] in wanted
                ]
            elif handle:
                normalized = f"@{handle.lstrip('@').lower()}"
                matches = [
                    channel for channel in self.channels
                    if str(channel.get("handle", "")).lower() == normalized
                ]
            else:
                matches = self.channels
            return httpx.Response(
                200,
                json={"items": [self._channel_wire(channel) for channel in matches]},
            )

        if path.endswith("/search"):
            query = request.url.params.get("q", "")
            language = request.url.params.get("relevanceLanguage")
            terms = [term.lower() for term in query.split() if term]
            matches = []
            for video in self.videos:
                if language and video["default_language"] != language:
                    continue
                searchable = " ".join(
                    [
                        video["title"],
                        video.get("description", ""),
                        " ".join(video.get("tags", [])),
                        video["channel_title"],
                    ]
                ).lower()
                if not terms or all(term in searchable for term in terms):
                    matches.append(video)
            max_results = int(request.url.params.get("maxResults", 25))
            try:
                start = int(request.url.params.get("pageToken", "0"))
            except ValueError:
                start = 0
            end = start + max_results
            payload = {
                "items": [
                    {"id": {"kind": "youtube#video", "videoId": video["video_id"]}}
                    for video in matches[start:end]
                ],
                "pageInfo": {
                    "totalResults": len(matches),
                    "resultsPerPage": max_results,
                },
            }
            if end < len(matches):
                payload["nextPageToken"] = str(end)
            return httpx.Response(200, json=payload)

        if path.endswith("/subscriptions"):
            channels = [
                channel for channel in self.channels
                if channel["channel_id"] in self.library["subscribed_channel_ids"]
            ]
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"channelId": channel["channel_id"]}
                            }
                        }
                        for channel in channels
                    ]
                },
            )

        if path.endswith("/playlists") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": playlist["playlist_id"],
                            "snippet": {
                                "title": playlist["title"],
                                "description": playlist["description"],
                            },
                            "contentDetails": {
                                "itemCount": playlist["item_count"]
                            },
                            "status": {
                                "privacyStatus": playlist["privacy_status"]
                            },
                        }
                        for playlist in self.library["playlists"]
                    ]
                    + list(self.created_playlists.values())
                },
            )

        if path.endswith("/playlists") and request.method == "POST":
            body = json.loads(request.content)
            snippet = body["snippet"]
            status = body["status"]
            self.counter += 1
            playlist_id = f"PLcontract{self.counter:03d}"
            wire = {
                "id": playlist_id,
                "snippet": snippet,
                "contentDetails": {"itemCount": 0},
                "status": status,
            }
            self.created_playlists[playlist_id] = wire
            self.created_items[playlist_id] = []
            return httpx.Response(200, json=wire)

        if path.endswith("/playlistItems") and request.method == "GET":
            playlist_id = request.url.params["playlistId"]
            ids = list(self.library["playlist_items"].get(playlist_id, []))
            ids.extend(self.created_items.get(playlist_id, []))
            max_results = int(request.url.params.get("maxResults", 50))
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"contentDetails": {"videoId": video_id}}
                        for video_id in ids[:max_results]
                    ]
                },
            )

        if path.endswith("/playlistItems") and request.method == "POST":
            body = json.loads(request.content)
            snippet = body["snippet"]
            playlist_id = snippet["playlistId"]
            video_id = snippet["resourceId"]["videoId"]
            self.created_items.setdefault(playlist_id, [])
            self.created_items[playlist_id].append(video_id)
            position = len(self.created_items[playlist_id]) - 1
            return httpx.Response(
                200,
                json={
                    "id": f"PLIcontract{len(self.created_items[playlist_id])}",
                    "snippet": {"position": position},
                },
            )

        return httpx.Response(404, json={"error": {"message": "Synthetic route not found"}})


def make_live_provider(
    tmp_path: Path,
    transport: httpx.BaseTransport,
) -> LiveYouTubeProvider:
    token_path = tmp_path / "oauth.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "synthetic-access-token",
                "refresh_token": "synthetic-refresh-token",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
            }
        ),
        encoding="utf-8",
    )
    client = httpx.Client(transport=transport)
    return LiveYouTubeProvider(
        api_key="synthetic-api-key",
        oauth_credentials_path=token_path,
        client_id="synthetic-client-id",
        client_secret="synthetic-client-secret",
        max_retries=3,
        base_backoff_seconds=0.001,
        http_client=client,
        sleep_fn=lambda _: None,
        jitter_fn=lambda _low, _high: 0.0,
    )


@pytest.fixture(params=["mock", "live"])
def provider(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    if request.param == "mock":
        return FixtureMockProvider(FIXTURES)
    wire = FixtureWireTransport()
    return make_live_provider(tmp_path, httpx.MockTransport(wire))


def test_get_videos_contract(provider: Any) -> None:
    videos = provider.get_videos(["vidDS000001", "vidTAG000008"])
    assert all(isinstance(video, VideoMetadata) for video in videos)
    assert videos[1].tags == []


def test_get_channels_contract(provider: Any) -> None:
    by_id = provider.get_channels(channel_ids=["UCsynthetic001"])
    assert len(by_id) == 1
    assert isinstance(by_id[0], ChannelMetadata)

    by_handle = provider.get_channels(handle="@python-studio")
    assert len(by_handle) == 1
    assert by_handle[0].channel_id == "UCsynthetic002"


def test_search_contract(provider: Any) -> None:
    spanish = provider.search_videos("sistemas", max_results=10, language="es")
    assert isinstance(spanish, SearchPage)
    assert spanish.video_ids == ["vidES000004"]

    first = provider.search_videos("python", max_results=2)
    assert isinstance(first, SearchPage)
    assert len(first.video_ids) == 2
    assert first.next_page_token is not None

    second = provider.search_videos(
        "python",
        max_results=2,
        page_token=first.next_page_token,
    )
    assert len(second.video_ids) > 0
    assert set(first.video_ids).isdisjoint(second.video_ids)


def test_user_library_contract(provider: Any) -> None:
    likes = provider.get_user_likes(3)
    subscriptions = provider.get_user_subscriptions(3)
    playlists = provider.get_user_playlists(10)
    items = provider.get_playlist_items("PLsynthetic001", 10)

    assert len(likes) == 3
    assert all(isinstance(video, VideoMetadata) for video in likes)
    assert len(subscriptions) == 3
    assert all(isinstance(channel, ChannelMetadata) for channel in subscriptions)
    assert len(playlists) == 2
    assert all(isinstance(playlist, PlaylistSummary) for playlist in playlists)
    assert len(items) == 4


def test_playlist_write_contract(provider: Any) -> None:
    created = provider.create_playlist(
        "Contract Playlist",
        description="Synthetic",
        privacy_status="private",
    )
    item = provider.add_playlist_item(created.playlist_id, "vidDS000001")

    assert isinstance(created, CreatedPlaylist)
    assert created.playlist_id
    assert created.url.startswith("https://www.youtube.com/playlist?list=")
    assert isinstance(item, PlaylistItemResult)
    assert item.playlist_id == created.playlist_id
    assert item.video_id == "vidDS000001"
    assert item.playlist_item_id


@pytest.mark.parametrize(
    ("fault_name", "error_payload_key", "error_class", "error_code"),
    [
        ("video_unavailable", "videoNotFound", VideoUnavailableError, "VIDEO_UNAVAILABLE"),
        ("quota_exceeded", "quotaExceeded", QuotaBudgetExceededError, "QUOTA_BUDGET_EXCEEDED"),
        (
            "youtube_signup_required",
            "youtubeSignupRequired",
            YouTubeSignupRequiredError,
            "YOUTUBE_SIGNUP_REQUIRED",
        ),
        (
            "invalid_grant",
            "invalid_grant",
            OAuthReauthorizationRequiredError,
            "OAUTH_REAUTH_REQUIRED",
        ),
    ],
)
def test_error_mapping_parity(
    tmp_path: Path,
    fault_name: str,
    error_payload_key: str,
    error_class: type[YouTubeMCPError],
    error_code: str,
) -> None:
    mock = FixtureMockProvider(FIXTURES)
    mock.inject_fault(fault_name)
    with pytest.raises(error_class) as mock_exc:
        mock.get_videos(["vidDS000001"])
    assert mock_exc.value.to_error_payload()["error_code"] == error_code

    errors = _load_json("error_payloads.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if error_payload_key == "invalid_grant":
            if request.url.host == "oauth2.googleapis.com":
                payload = errors["invalid_grant"]
                return httpx.Response(400, json=payload)
        elif error_payload_key == "youtubeSignupRequired":
            return httpx.Response(
                403,
                json=errors["youtubeSignupRequired"],
            )
        elif error_payload_key == "quotaExceeded":
            return httpx.Response(
                403,
                json=errors["quotaExceeded"],
            )
        elif error_payload_key == "videoNotFound":
            return httpx.Response(
                404,
                json=errors["videoNotFound"],
            )
        return httpx.Response(404, json=errors["videoNotFound"])

    live = make_live_provider(tmp_path, httpx.MockTransport(handler))
    if error_payload_key == "invalid_grant":
        token_path = live.oauth_credentials_path
        assert token_path is not None
        token_path.write_text(
            json.dumps(
                {
                    "access_token": "old-synthetic-access",
                    "refresh_token": "synthetic-refresh-secret",
                    "expires_at": "2000-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        live._oauth_data = live._load_oauth_data()

    with pytest.raises(error_class) as live_exc:
        if error_payload_key == "invalid_grant":
            live.get_user_likes()
        else:
            live.get_videos(["vidDS000001"])
    assert live_exc.value.to_error_payload()["error_code"] == error_code


@pytest.mark.parametrize("status_code", [400, 403, 404])
def test_non_transient_4xx_is_not_retried(status_code: int) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, json={"error": {"message": "Synthetic failure"}})

    provider = LiveYouTubeProvider(
        api_key="synthetic-api-key",
        max_retries=3,
        base_backoff_seconds=0.001,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=lambda _: None,
        jitter_fn=lambda _low, _high: 0.0,
    )
    with pytest.raises(YouTubeMCPError):
        provider.get_videos(["vidDS000001"])
    assert attempts == 1


@pytest.mark.parametrize("status_code", [429, 503])
def test_transient_retries_succeed(status_code: int) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"items": [_fixture_video_wire()]})

    provider = LiveYouTubeProvider(
        api_key="synthetic-api-key",
        max_retries=3,
        base_backoff_seconds=0.001,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=sleeps.append,
        jitter_fn=lambda _low, _high: 0.0,
    )
    videos = provider.get_videos(["vidDS000001"])
    assert len(videos) == 1
    assert attempts == 2
    assert len(sleeps) == 1


def _fixture_video_wire() -> dict[str, Any]:
    video = _load_json("videos.json")[0]
    return {
        "id": video["video_id"],
        "snippet": {
            "title": video["title"],
            "description": video["description"],
            "channelId": video["channel_id"],
            "channelTitle": video["channel_title"],
            "categoryId": video["category_id"],
            "tags": video["tags"],
            "publishedAt": video["published_at"],
        },
        "contentDetails": {"duration": video["duration_iso"]},
        "statistics": {"viewCount": "1", "likeCount": "1"},
        "topicDetails": {},
    }


def test_max_retries_is_bounded_and_secret_safe(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            503,
            json={"error": {"message": "synthetic-secret-token-must-not-leak"}},
        )

    provider = LiveYouTubeProvider(
        api_key="synthetic-api-key-secret",
        max_retries=2,
        base_backoff_seconds=0.001,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=lambda _: None,
        jitter_fn=lambda _low, _high: 0.0,
    )
    caplog.set_level(logging.INFO)
    with pytest.raises(YouTubeMCPError) as exc_info:
        provider.get_videos(["vidDS000001"])

    payload_text = json.dumps(exc_info.value.to_error_payload())
    assert attempts == 3
    assert "synthetic-api-key-secret" not in payload_text
    assert "synthetic-secret-token-must-not-leak" not in payload_text
    assert "synthetic-api-key-secret" not in caplog.text
    assert "synthetic-refresh-secret" not in caplog.text


def test_oauth_401_refreshes_once_and_invalid_grant_is_safe(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token_path = tmp_path / "oauth.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "synthetic-old-access",
                "refresh_token": "synthetic-refresh-secret",
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    api_attempts = 0
    refresh_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal api_attempts, refresh_attempts
        if request.url.host == "oauth2.googleapis.com":
            refresh_attempts += 1
            return httpx.Response(
                200,
                json={
                    "access_token": "synthetic-new-access",
                    "expires_in": 3600,
                },
            )
        api_attempts += 1
        if api_attempts == 1:
            return httpx.Response(401, json={"error": {"message": "synthetic unauthorized"}})
        return httpx.Response(200, json={"items": [_fixture_video_wire()]})

    provider = LiveYouTubeProvider(
        oauth_credentials_path=token_path,
        client_id="synthetic-client-id",
        client_secret="synthetic-client-secret",
        max_retries=2,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_fn=lambda _: None,
        jitter_fn=lambda _low, _high: 0.0,
    )
    caplog.set_level(logging.INFO)
    videos = provider.get_user_likes()
    assert len(videos) == 1
    assert api_attempts == 2
    assert refresh_attempts == 1

    failed_attempts = 0

    def invalid_handler(request: httpx.Request) -> httpx.Response:
        nonlocal failed_attempts
        failed_attempts += 1
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "synthetic refresh failed"},
        )

    token_path.write_text(
        json.dumps(
            {
                "access_token": "synthetic-old-access",
                "refresh_token": "synthetic-refresh-secret",
                "expires_at": "2000-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    failed = LiveYouTubeProvider(
        oauth_credentials_path=token_path,
        client_id="synthetic-client-id",
        client_secret="synthetic-client-secret",
        max_retries=2,
        http_client=httpx.Client(transport=httpx.MockTransport(invalid_handler)),
        sleep_fn=lambda _: None,
        jitter_fn=lambda _low, _high: 0.0,
    )
    with pytest.raises(OAuthReauthorizationRequiredError) as exc_info:
        failed.get_user_likes()
    payload_text = json.dumps(exc_info.value.to_error_payload())
    assert "synthetic-refresh-secret" not in payload_text
    assert "synthetic-client-secret" not in payload_text
    assert "synthetic-refresh-secret" not in caplog.text
    assert "synthetic-client-secret" not in caplog.text


def test_static_provider_import_boundary() -> None:
    forbidden_roots = {
        "httpx",
        "googleapiclient",
        "google",
        "google_auth_oauthlib",
        "requests",
        "urllib3",
        "yt_dlp",
        "pytube",
    }
    source_root = ROOT / "src" / "youtube_mcp"
    providers_root = source_root / "providers"

    for path in source_root.rglob("*.py"):
        if path.is_relative_to(providers_root):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".", 1)[0]}
            else:
                continue
            forbidden = roots & forbidden_roots
            assert not forbidden, f"{path.relative_to(ROOT)} imports {sorted(forbidden)}"
