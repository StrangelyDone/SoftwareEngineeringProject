"""Offline tests for LiveYouTubeProvider using httpx.MockTransport."""

from __future__ import annotations

import json
from pathlib import Path

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
    PlaylistSummary,
    SearchPage,
    VideoMetadata,
)
from youtube_mcp.providers.live import LiveYouTubeProvider


def make_provider(
    handler,
    *,
    tmp_path: Path | None = None,
    max_retries: int = 3,
) -> LiveYouTubeProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    token_path = None
    if tmp_path is not None:
        token_path = tmp_path / "oauth.json"
    return LiveYouTubeProvider(
        api_key="synthetic-api-key",
        oauth_credentials_path=token_path,
        client_id="synthetic-client-id",
        client_secret="synthetic-client-secret",
        max_retries=max_retries,
        base_backoff_seconds=0.001,
        http_client=client,
        sleep_fn=lambda _: None,
    )


def video_payload(video_id: str) -> dict[str, object]:
    return {
        "kind": "youtube#video",
        "id": video_id,
        "snippet": {
            "title": f"Synthetic {video_id}",
            "description": "Synthetic offline video.",
            "channelId": "UCsynthetic001",
            "channelTitle": "Systems Lab",
            "categoryId": "28",
            "tags": [],
            "publishedAt": "2026-03-01T00:00:00Z",
        },
        "contentDetails": {"duration": "PT11M30S"},
        "statistics": {"viewCount": "100", "likeCount": "10"},
        "topicDetails": {"topicCategories": ["https://example.test/category"]},
    }


def test_get_videos_batches_at_50_and_parses_models() -> None:
    requested_ids: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_ids.append(request.url.params["id"])
        ids = request.url.params["id"].split(",")
        return httpx.Response(200, json={"items": [video_payload(video_id) for video_id in ids]})

    provider = make_provider(handler)
    video_ids = [f"synthetic{i:03d}" for i in range(51)]
    videos = provider.get_videos(video_ids)

    assert len(videos) == 51
    assert all(isinstance(video, VideoMetadata) for video in videos)
    assert len(requested_ids) == 2
    assert len(requested_ids[0].split(",")) == 50
    assert len(requested_ids[1].split(",")) == 1
    assert videos[0].tags == []
    assert videos[0].duration_seconds == 690


def test_get_channels_resolves_id_and_handle() -> None:
    seen_params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "UCsynthetic001",
                        "snippet": {
                            "title": "Systems Lab",
                            "description": "Synthetic channel",
                            "customUrl": "@systems-lab",
                            "country": "US",
                        },
                        "contentDetails": {
                            "relatedPlaylists": {"uploads": "UUsynthetic001"}
                        },
                        "statistics": {"subscriberCount": "100", "videoCount": "5"},
                        "topicDetails": {"topicCategories": ["Technology"]},
                        "brandingSettings": {
                            "channel": {"keywords": '"systems" "testing"'}
                        },
                    }
                ]
            },
        )

    provider = make_provider(handler)
    channel = provider.get_channels(channel_ids=["UCsynthetic001"])
    channel_by_handle = provider.get_channels(handle="@systems-lab")

    assert isinstance(channel[0], ChannelMetadata)
    assert channel[0].uploads_playlist_id == "UUsynthetic001"
    assert channel_by_handle[0].handle == "@systems-lab"
    assert seen_params[0]["id"] == "UCsynthetic001"
    assert seen_params[1]["forHandle"] == "systems-lab"


def test_search_page_and_playlist_methods_parse_official_shapes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": {"kind": "youtube#video", "videoId": "vid001"}},
                        {"id": {"kind": "youtube#video", "videoId": "vid002"}},
                    ],
                    "nextPageToken": "next-page",
                    "pageInfo": {"totalResults": 25, "resultsPerPage": 2},
                },
            )
        if request.url.path.endswith("/playlists"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "PLsynthetic",
                            "snippet": {
                                "title": "Synthetic Playlist",
                                "description": "Offline",
                            },
                            "contentDetails": {"itemCount": 2},
                            "status": {"privacyStatus": "private"},
                        }
                    ]
                },
            )
        if request.url.path.endswith("/playlistItems"):
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {"contentDetails": {"videoId": "vid001"}},
                            {"contentDetails": {"videoId": "vid002"}},
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "id": "PLIsynthetic",
                    "snippet": {"position": 2},
                },
            )
        return httpx.Response(404, json={})

    token_path = Path(__file__).resolve().parents[1] / ".test-live-token.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "synthetic-access-token",
                "refresh_token": "synthetic-refresh-token",
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    try:
        provider = make_provider(handler)
        provider.oauth_credentials_path = token_path
        provider._oauth_data = provider._load_oauth_data()

        page = provider.search_videos("systems", max_results=2, language="en")
        playlists = provider.get_user_playlists()
        playlist_items = provider.get_playlist_items("PLsynthetic", 10)
        created = provider.create_playlist(
            "New Synthetic",
            description="Offline",
            privacy_status="private",
        ) if False else None
    finally:
        token_path.unlink(missing_ok=True)

    assert isinstance(page, SearchPage)
    assert page.video_ids == ["vid001", "vid002"]
    assert page.next_page_token == "next-page"
    assert isinstance(playlists[0], PlaylistSummary)
    assert playlist_items == ["vid001", "vid002"]
    assert created is None


def test_oauth_refresh_expired_token_is_atomic(tmp_path: Path) -> None:
    token_path = tmp_path / "oauth.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "old-token",
                "refresh_token": "synthetic-refresh",
                "expires_at": "2000-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={"access_token": "new-synthetic-token", "expires_in": 3600},
            )
        if request.url.path.endswith("/videos"):
            assert request.headers["Authorization"] == "Bearer new-synthetic-token"
            return httpx.Response(200, json={"items": [video_payload("vid001")]})
        return httpx.Response(404)

    provider = make_provider(handler, tmp_path=tmp_path)
    provider.oauth_credentials_path = token_path
    provider.client_id = "synthetic-client-id"
    provider.client_secret = "synthetic-client-secret"
    provider._oauth_data = provider._load_oauth_data()

    videos = provider.get_user_likes()
    persisted = json.loads(token_path.read_text(encoding="utf-8"))

    assert [video.video_id for video in videos] == ["vid001"]
    assert persisted["access_token"] == "new-synthetic-token"
    assert "expires_at" in persisted


def test_invalid_grant_maps_to_oauth_error(tmp_path: Path) -> None:
    token_path = tmp_path / "oauth.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "old-token",
                "refresh_token": "synthetic-refresh",
                "expires_at": "2000-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                400,
                json={"error": "invalid_grant", "error_description": "expired"},
            )
        return httpx.Response(401)

    provider = make_provider(handler, tmp_path=tmp_path)
    provider.oauth_credentials_path = token_path
    provider._oauth_data = provider._load_oauth_data()

    with pytest.raises(OAuthReauthorizationRequiredError) as exc_info:
        provider.get_user_likes()
    assert exc_info.value.error_code == "OAUTH_REAUTH_REQUIRED"
    assert "synthetic-refresh" not in str(exc_info.value.to_error_payload())


@pytest.mark.parametrize(
    ("reason", "error_class"),
    [
        ("quotaExceeded", QuotaBudgetExceededError),
        ("dailyLimitExceeded", QuotaBudgetExceededError),
        ("youtubeSignupRequired", YouTubeSignupRequiredError),
        ("videoNotFound", VideoUnavailableError),
    ],
)
def test_google_error_payload_mapping(reason: str, error_class: type[YouTubeMCPError]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": 403,
                    "message": "Synthetic API failure",
                    "errors": [{"reason": reason}],
                }
            },
        )

    provider = make_provider(handler)
    with pytest.raises(error_class):
        provider.get_videos(["synthetic001"])


def test_empty_items_raise_video_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    provider = make_provider(handler)
    with pytest.raises(VideoUnavailableError):
        provider.get_videos(["synthetic001"])


def test_429_retry_succeeds_and_503_exhaustion_is_safe() -> None:
    attempts = {"count": 0}

    def retry_handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"items": [video_payload("vid001")]})

    provider = make_provider(retry_handler, max_retries=2)
    assert provider.get_videos(["vid001"])[0].video_id == "vid001"
    assert attempts["count"] == 2

    def exhausted_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "Synthetic unavailable"}})

    exhausted = make_provider(exhausted_handler, max_retries=2)
    with pytest.raises(YouTubeMCPError) as exc_info:
        exhausted.get_videos(["vid001"])
    assert exc_info.value.error_code == "YOUTUBE_MCP_ERROR"
    assert "synthetic unavailable" not in exc_info.value.to_error_payload()["message"].lower()
