"""Offline tests for safe FastMCP error results."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from mcp.types import CallToolResult

from youtube_mcp.config import Settings
from youtube_mcp.exceptions import (
    ConfirmationRequiredError,
    InvalidVideoIdentifierError,
    OAuthReauthorizationRequiredError,
    QuotaBudgetExceededError,
    VideoUnavailableError,
    YouTubeSignupRequiredError,
)
from youtube_mcp.server import create_app

DOMAIN_ERROR_CASES = [
    (
        "find_similar_videos",
        "similarity",
        "find_similar_videos",
        {"video_ref": "dQw4w9WgXcQ"},
        InvalidVideoIdentifierError,
    ),
    (
        "find_similar_channels",
        "similarity",
        "find_similar_channels",
        {"channel_ref": "@fixture"},
        VideoUnavailableError,
    ),
    (
        "get_recommendations",
        "recommendations",
        "recommend_for_user",
        {},
        QuotaBudgetExceededError,
    ),
    (
        "analyze_user_engagement",
        "analytics",
        "analyze_engagement",
        {},
        ConfirmationRequiredError,
    ),
    (
        "propose_playlist",
        "playlists",
        "propose_playlist",
        {"topic": "systems", "max_total_duration_minutes": 30},
        OAuthReauthorizationRequiredError,
    ),
    (
        "confirm_playlist",
        "playlists",
        "confirm_playlist",
        {
            "confirmation_token": "fixture-token",
            "playlist_title": "Fixture playlist",
            "user_confirmed": True,
        },
        YouTubeSignupRequiredError,
    ),
]


def _app(tmp_path: Path):
    return create_app(
        settings=Settings(database_url=f"sqlite:///{tmp_path / 'errors.db'}")
    )


@pytest.mark.parametrize(
    ("tool_name", "service_name", "method_name", "arguments", "error_type"),
    DOMAIN_ERROR_CASES,
)
def test_domain_errors_return_structured_mcp_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    service_name: str,
    method_name: str,
    arguments: dict[str, Any],
    error_type: type[Exception],
) -> None:
    app = _app(tmp_path)
    error = error_type("Safe domain message", "Safe remediation")
    service = getattr(app.state.services, service_name)

    def raise_domain_error(*_args: Any, **_kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(service, method_name, raise_domain_error)
    result = asyncio.run(app.state.mcp.call_tool(tool_name, arguments))

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    payload = json.loads(result.content[0].text)
    assert payload == error.to_error_payload()
    assert set(payload) == {"error_code", "message", "remediation"}
    assert result.structuredContent == {"result": payload}


@pytest.mark.parametrize(
    "arguments",
    [
        {"confirmation_token": "fixture-token", "playlist_title": "Fixture playlist"},
        {
            "confirmation_token": "fixture-token",
            "playlist_title": "Fixture playlist",
            "user_confirmed": False,
        },
    ],
)
def test_confirmation_false_or_missing_returns_confirmation_error(
    tmp_path: Path,
    arguments: dict[str, Any],
) -> None:
    app = _app(tmp_path)

    result = asyncio.run(app.state.mcp.call_tool("confirm_playlist", arguments))

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    payload = json.loads(result.content[0].text)
    assert payload["error_code"] == "CONFIRMATION_REQUIRED"
    assert set(payload) == {"error_code", "message", "remediation"}


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_unexpected_error_is_logged_but_not_returned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error_type: type[Exception],
) -> None:
    app = _app(tmp_path)
    secret_like_detail = "TOKEN=do-not-return /private/local/path"

    def raise_unexpected(*_args: Any, **_kwargs: Any) -> None:
        raise error_type(secret_like_detail)

    monkeypatch.setattr(
        app.state.services.similarity,
        "find_similar_videos",
        raise_unexpected,
    )
    result = asyncio.run(
        app.state.mcp.call_tool(
            "find_similar_videos",
            {"video_ref": "dQw4w9WgXcQ"},
        )
    )

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    payload = json.loads(result.content[0].text)
    assert payload == {
        "error_code": "INTERNAL_ERROR",
        "message": "An unexpected error occurred while processing the request.",
        "remediation": "Check the request and try again. Contact support if the issue persists.",
    }
    assert secret_like_detail not in result.content[0].text
    assert secret_like_detail in caplog.text
