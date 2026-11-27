"""Offline tests for M2.1 provider models, exceptions, and ABC contract."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

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
from youtube_mcp.providers.mock import FixtureMockProvider

EXPECTED_METHODS = {
    "get_videos",
    "get_channels",
    "search_videos",
    "get_user_likes",
    "get_user_subscriptions",
    "get_user_playlists",
    "get_playlist_items",
    "create_playlist",
    "add_playlist_item",
}

EXPECTED_ERRORS = {
    InvalidVideoIdentifierError: ("INVALID_IDENTIFIER", "Provide a valid YouTube URL"),
    VideoUnavailableError: ("VIDEO_UNAVAILABLE", "Verify the video is public/accessible"),
    QuotaBudgetExceededError: (
        "QUOTA_BUDGET_EXCEEDED",
        "Wait for UTC midnight quota reset",
    ),
    ConfirmationRequiredError: (
        "CONFIRMATION_REQUIRED",
        "Re-run propose_playlist",
    ),
    OAuthReauthorizationRequiredError: (
        "OAUTH_REAUTH_REQUIRED",
        "Re-run the local OAuth 2.0 authorization flow",
    ),
    YouTubeSignupRequiredError: (
        "YOUTUBE_SIGNUP_REQUIRED",
        "Create a YouTube channel",
    ),
}


def test_provider_abc_cannot_be_instantiated_and_exposes_expected_methods() -> None:
    with pytest.raises(TypeError):
        YouTubeProvider()  # type: ignore[abstract]

    abstract_methods = {
        name
        for name, method in YouTubeProvider.__dict__.items()
        if getattr(method, "__isabstractmethod__", False)
    }
    assert abstract_methods == EXPECTED_METHODS

    public_methods = {
        name
        for name in YouTubeProvider.__dict__
        if not name.startswith("_")
    }
    assert not any(name.startswith("delete_") for name in public_methods)
    assert not any(
        name.startswith(("update_subscription", "delete_playlist"))
        for name in public_methods
    )


def test_fixture_mock_provider_remains_instantiable() -> None:
    assert isinstance(FixtureMockProvider(), YouTubeProvider)


@pytest.mark.parametrize(("error_class", "expected"), EXPECTED_ERRORS.items())
def test_exception_hierarchy_and_safe_payload(
    error_class: type[YouTubeMCPError],
    expected: tuple[str, str],
) -> None:
    error = error_class()
    assert isinstance(error, YouTubeMCPError)
    assert error.error_code == expected[0]
    assert expected[1] in error.remediation

    payload = error.to_error_payload()
    assert set(payload) == {"error_code", "message", "remediation"}
    assert all(isinstance(value, str) for value in payload.values())
    assert "Traceback" not in payload["message"]

    custom = error_class("custom safe message", "custom safe remediation")
    assert custom.message == "custom safe message"
    assert custom.remediation == "custom safe remediation"
    assert custom.to_payload() == custom.to_error_payload()


def test_video_metadata_defaults_aliases_validation_and_serialization() -> None:
    video = VideoMetadata(video_id="dQw4w9WgXcQ", title="Offline")
    assert video.tags == []
    assert video.description == ""
    assert video.duration_iso is None
    assert "video_id" in video.model_dump()
    assert "tags" in video.model_dump_json()

    compatible = VideoMetadata(
        video_id="dQw4w9WgXcQ",
        title="Offline",
        duration_iso8601="PT10M",
        tags=["mcp"],
    )
    assert compatible.duration_iso == "PT10M"
    assert compatible.duration_iso8601 == "PT10M"

    with pytest.raises(ValidationError):
        VideoMetadata(video_id=None, title="Invalid")  # type: ignore[arg-type]


def test_channel_metadata_defaults_aliases_and_serialization() -> None:
    channel = ChannelMetadata(channel_id="UC123", title="Channel", topics=["Technology"])
    assert channel.keywords == ["Technology"]
    assert channel.topic_categories == []
    assert channel.topics == ["Technology"]
    assert "channel_id" in channel.model_dump()


def test_search_page_aliases_and_serialization() -> None:
    page = SearchPage(items=["dQw4w9WgXcQ"], next_page_token="next", total_results=1)
    assert page.video_ids == ["dQw4w9WgXcQ"]
    assert page.items == ["dQw4w9WgXcQ"]
    assert "video_ids" in page.model_dump()


def test_playlist_models_validate_defaults_and_serialize() -> None:
    summary = PlaylistSummary(playlist_id="PL1", title="Offline")
    assert summary.item_count == 0
    assert "playlist_id" in summary.model_dump()

    created = CreatedPlaylist(
        playlist_id="PL1",
        title="Offline",
        playlist_url="https://www.youtube.com/playlist?list=PL1",
    )
    assert created.url.endswith("PL1")
    assert created.playlist_url == created.url
    assert "playlist_id" in created.model_dump()

    item = PlaylistItemResult(
        playlist_id="PL1",
        video_id="dQw4w9WgXcQ",
        playlist_item_id="PLI1",
        position=3,
    )
    assert item.position == 3
    assert "playlist_item_id" in item.model_dump_json()


@pytest.mark.parametrize(
    "relative_path",
    [
        "src/youtube_mcp/models.py",
        "src/youtube_mcp/exceptions.py",
        "src/youtube_mcp/providers/base.py",
    ],
)
def test_provider_contract_modules_have_no_external_http_imports(relative_path: str) -> None:
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / relative_path).read_text(encoding="utf-8"), filename=relative_path)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert "httpx" not in imported_roots
    assert "googleapiclient" not in imported_roots
    assert "google" not in imported_roots
