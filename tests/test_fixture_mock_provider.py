"""Offline tests for the sanitized fixture corpus and FixtureMockProvider."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

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
from youtube_mcp.providers.mock import FixtureMockProvider

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|oauth[_-]?token|client[_-]?secret)"
)


@pytest.fixture
def provider() -> FixtureMockProvider:
    return FixtureMockProvider(FIXTURES)


def test_fixture_json_files_are_clean_and_parseable() -> None:
    fixture_files = sorted(FIXTURES.glob("*.json"))
    assert fixture_files

    for fixture_path in fixture_files:
        text = fixture_path.read_text(encoding="utf-8")
        assert json.loads(text) is not None
        assert not SECRET_PATTERN.search(text), f"Secret-like key in {fixture_path.name}"

    videos = json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))
    channels = json.loads((FIXTURES / "channels.json").read_text(encoding="utf-8"))
    library = json.loads((FIXTURES / "user_library.json").read_text(encoding="utf-8"))

    assert len(videos) >= 12
    assert len(channels) >= 5
    assert all(VideoMetadata.model_validate(video).video_id for video in videos)
    assert all(ChannelMetadata.model_validate(channel).channel_id for channel in channels)
    assert all(
        PlaylistSummary.model_validate(playlist)
        for playlist in library["playlists"]
    )

    languages = {video["default_language"] for video in videos}
    assert {"en", "es", "de"}.issubset(languages)
    assert {"PT4M15S", "PT11M30S", "PT18M45S", "PT42M00S", "PT1H10M05S"}.issubset(
        {video.get("duration_iso") for video in videos}
    )
    assert sum(not video.get("tags") for video in videos) >= 2


def test_get_videos_returns_typed_matches_and_missing_tags(
    provider: FixtureMockProvider,
) -> None:
    videos = provider.get_videos(["vidDS000001", "vidTAG000008"])
    assert all(isinstance(video, VideoMetadata) for video in videos)
    assert videos[0].video_id == "vidDS000001"
    assert videos[1].tags == []

    sparse = provider.get_videos(["vidSPARSE010"])[0]
    assert sparse.description == ""
    assert sparse.duration_iso is None

    malformed = provider.get_videos(["vidBADUR011"])[0]
    assert malformed.duration_iso == "not-an-iso-duration"

    with pytest.raises(VideoUnavailableError):
        provider.get_videos(["missing-video"])
    with pytest.raises(VideoUnavailableError):
        provider.get_videos(["vidPRIVATE001"])


def test_get_channels_resolves_ids_and_handles(provider: FixtureMockProvider) -> None:
    by_id = provider.get_channels(channel_ids=["UCsynthetic001"])
    assert len(by_id) == 1
    assert isinstance(by_id[0], ChannelMetadata)

    by_handle = provider.get_channels(handle="@PYTHON-STUDIO")
    assert len(by_handle) == 1
    assert by_handle[0].channel_id == "UCsynthetic002"

    with pytest.raises(VideoUnavailableError):
        provider.get_channels(channel_ids=["UCmissing"])
    with pytest.raises(VideoUnavailableError):
        provider.get_channels(handle="@missing-channel")


def test_search_respects_query_language_pagination_and_limit(
    provider: FixtureMockProvider,
) -> None:
    spanish = provider.search_videos("sistemas", max_results=10, language="es")
    assert isinstance(spanish, SearchPage)
    assert spanish.total_results == 1
    assert spanish.video_ids == ["vidES000004"]

    page_one = provider.search_videos("python", max_results=2)
    assert page_one.next_page_token is not None
    assert len(page_one.video_ids) == 2

    page_two = provider.search_videos(
        "python",
        max_results=2,
        page_token=page_one.next_page_token,
    )
    assert len(page_two.video_ids) > 0
    assert set(page_one.video_ids).isdisjoint(page_two.video_ids)

    no_match = provider.search_videos("no-such-synthetic-topic", max_results=5)
    assert no_match.video_ids == []
    assert no_match.next_page_token is None


def test_user_library_methods_return_typed_results(provider: FixtureMockProvider) -> None:
    likes = provider.get_user_likes(max_results=3)
    assert len(likes) == 3
    assert all(isinstance(video, VideoMetadata) for video in likes)

    subscriptions = provider.get_user_subscriptions(max_results=2)
    assert len(subscriptions) == 2
    assert all(isinstance(channel, ChannelMetadata) for channel in subscriptions)

    playlists = provider.get_user_playlists(max_results=10)
    assert len(playlists) >= 2
    assert all(isinstance(playlist, PlaylistSummary) for playlist in playlists)

    engineering_items = provider.get_playlist_items("PLsynthetic001", max_results=10)
    assert engineering_items == [
        "vidDS000001",
        "vidPY000002",
        "vidSQL00003",
        "vidPY000012",
    ]
    assert provider.get_playlist_items("UUsynthetic003", max_results=10)


def test_create_and_add_playlist_are_in_memory_only(
    provider: FixtureMockProvider,
) -> None:
    created = provider.create_playlist(
        "Synthetic Playlist",
        description="No disk mutation",
        privacy_status="private",
    )
    assert isinstance(created, CreatedPlaylist)
    assert created.playlist_id.startswith("PLmockcreated")

    item = provider.add_playlist_item(created.playlist_id, "vidPY000002")
    assert isinstance(item, PlaylistItemResult)
    assert item.playlist_id == created.playlist_id
    assert item.video_id == "vidPY000002"
    assert item.position == 0

    assert provider.get_playlist_items(created.playlist_id) == ["vidPY000002"]
    summaries = provider.get_user_playlists(max_results=10)
    created_summary = next(
        playlist for playlist in summaries if playlist.playlist_id == created.playlist_id
    )
    assert created_summary.item_count == 1


@pytest.mark.parametrize(
    ("fault_name", "error_class"),
    [
        ("video_unavailable", VideoUnavailableError),
        ("quota_exceeded", QuotaBudgetExceededError),
        ("youtube_signup_required", YouTubeSignupRequiredError),
        ("oauth_reauth_required", OAuthReauthorizationRequiredError),
        ("invalid_grant", OAuthReauthorizationRequiredError),
        ("invalid_identifier", InvalidVideoIdentifierError),
        ("confirmation_required", ConfirmationRequiredError),
    ],
)
def test_inject_fault_supported_modes(
    provider: FixtureMockProvider,
    fault_name: str,
    error_class: type[Exception],
) -> None:
    provider.inject_fault(fault_name)
    with pytest.raises(error_class):
        provider.get_videos(["vidDS000001"])


def test_inject_fault_clear_and_unknown(provider: FixtureMockProvider) -> None:
    provider.inject_fault("quota_exceeded")
    provider.inject_fault(None)
    assert provider.get_videos(["vidDS000001"])

    with pytest.raises(ValueError, match="Unknown fixture fault mode"):
        provider.inject_fault("typo_fault")
