"""Offline end-to-end tests through the in-process FastMCP protocol (`TQ-3`)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from mcp.types import CallToolResult

from youtube_mcp.config import Settings
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.server import create_app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPECTED_TOOLS = {
    "find_similar_videos",
    "find_similar_channels",
    "get_recommendations",
    "analyze_user_engagement",
    "propose_playlist",
    "confirm_playlist",
}


class E2EFixtureProvider(FixtureMockProvider):
    """Fixture adapter that records all reads and writes for offline assertions."""

    def __init__(self) -> None:
        super().__init__(FIXTURES)
        self.write_calls: list[str] = []

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ):
        created = super().create_playlist(title, description, privacy_status)
        self.write_calls.append("playlists.insert")
        return created

    def add_playlist_item(self, playlist_id: str, video_id: str):
        item = super().add_playlist_item(playlist_id, video_id)
        self.write_calls.append("playlistItems.insert")
        return item


def _make_app(tmp_path: Path, provider: E2EFixtureProvider | None = None):
    repository = SQLiteRepository(tmp_path / "mcp-e2e.db")
    repository.initialize_schema()
    fixture_provider = provider or E2EFixtureProvider()
    app = create_app(
        settings=Settings(
            database_url=f"sqlite:///{tmp_path / 'unused.db'}",
            daily_quota_budget=10_000,
        ),
        provider=fixture_provider,
        repository=repository,
    )
    return app, fixture_provider, repository


def _call(app: Any, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
    result = asyncio.run(app.state.mcp.call_tool(tool_name, arguments))
    if isinstance(result, tuple):
        content, structured_content = result
        return CallToolResult(
            content=content,
            structuredContent=structured_content,
        )
    assert isinstance(result, CallToolResult)
    return result


def _success_payload(result: CallToolResult) -> dict[str, Any]:
    assert result.isError is not True
    assert result.structuredContent is not None
    payload = result.structuredContent["result"]
    assert isinstance(payload, dict)
    return payload


def test_all_tools_are_registered_with_valid_draft_2020_12_schemas(
    tmp_path: Path,
) -> None:
    app, _, _ = _make_app(tmp_path)
    tools = asyncio.run(app.state.mcp.list_tools())

    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.outputSchema is not None
        Draft202012Validator.check_schema(tool.inputSchema)
        Draft202012Validator.check_schema(tool.outputSchema)


def test_all_six_tools_complete_offline_mcp_protocol_flows(tmp_path: Path) -> None:
    app, provider, repo = _make_app(tmp_path)

    videos = _success_payload(
        _call(
            app,
            "find_similar_videos",
            {"video_ref": "vidPY000002", "limit": 5},
        )
    )
    assert videos["seed_video_id"] == "vidPY000002"
    assert videos["results"]

    channels = _success_payload(
        _call(
            app,
            "find_similar_channels",
            {"channel_ref": "@systems-lab", "limit": 5},
        )
    )
    assert channels["seed_channel_id"] == "UCsynthetic001"
    assert isinstance(channels["results"], list)

    recommendations = _success_payload(
        _call(app, "get_recommendations", {"limit": 5})
    )
    assert recommendations["recommendations"]
    assert all(item["explanation"] for item in recommendations["recommendations"])

    engagement = _success_payload(
        _call(
            app,
            "analyze_user_engagement",
            {"period_days": 30, "compare_previous_period": True},
        )
    )
    assert engagement["unique_video_count"] > 0
    assert engagement["duration_preferences"]["valid_video_count"] > 0

    proposal = _success_payload(
        _call(
            app,
            "propose_playlist",
            {
                "topic": "python",
                "max_total_duration_minutes": 60,
                "max_video_duration_minutes": 45,
                "language": "en",
            },
        )
    )
    assert proposal["requires_explicit_user_confirmation"] is True
    assert proposal["proposed_videos"]
    assert repo.get_pending_playlist(proposal["confirmation_token"]).status == "PENDING"

    assert provider.write_calls == []
    created = _success_payload(
        _call(
            app,
            "confirm_playlist",
            {
                "confirmation_token": proposal["confirmation_token"],
                "playlist_title": "Offline Python Playlist",
                "user_confirmed": True,
            },
        )
    )
    assert created["status"] == "COMPLETED"
    assert created["items_added"] == len(proposal["proposed_videos"])
    assert created["quota_used"] == 50 + 50 * created["items_added"]
    assert len(provider.write_calls) == created["items_added"] + 1
    assert repo.get_pending_playlist(proposal["confirmation_token"]).status == "COMPLETED"


@pytest.mark.parametrize(
    ("tool_name", "fault", "arguments", "expected_code", "expected_message", "setup"),
    [
        (
            "find_similar_videos",
            "invalid_identifier",
            {"video_ref": "vidPY000002"},
            "INVALID_IDENTIFIER",
            "Injected offline fixture fault: invalid_identifier",
            None,
        ),
        (
            "find_similar_channels",
            "video_unavailable",
            {"channel_ref": "@systems-lab"},
            "VIDEO_UNAVAILABLE",
            "Injected offline fixture fault: video_unavailable",
            None,
        ),
        (
            "get_recommendations",
            "quota_exceeded",
            {},
            "QUOTA_BUDGET_EXCEEDED",
            "Injected offline fixture fault: quota_exceeded",
            None,
        ),
        (
            "confirm_playlist",
            None,
            {
                "confirmation_token": "unneeded-when-unconfirmed",
                "playlist_title": "No Playlist",
                "user_confirmed": False,
            },
            "CONFIRMATION_REQUIRED",
            "Explicit user_confirmed=True is required before creating a YouTube playlist.",
            None,
        ),
        (
            "analyze_user_engagement",
            "oauth_reauth_required",
            {},
            "OAUTH_REAUTH_REQUIRED",
            "Injected offline fixture fault: oauth_reauth_required",
            None,
        ),
        (
            "confirm_playlist",
            "youtube_signup_required",
            {},
            "YOUTUBE_SIGNUP_REQUIRED",
            "Injected offline fixture fault: youtube_signup_required",
            "propose",
        ),
    ],
)
def test_domain_errors_are_safe_structured_mcp_results(
    tmp_path: Path,
    tool_name: str,
    fault: str | None,
    arguments: dict[str, Any],
    expected_code: str,
    expected_message: str,
    setup: str | None,
) -> None:
    provider = E2EFixtureProvider()
    app, _, repo = _make_app(tmp_path, provider)

    if setup == "propose":
        proposal = _success_payload(
            _call(
                app,
                "propose_playlist",
                {
                    "topic": "python",
                    "max_total_duration_minutes": 60,
                    "max_video_duration_minutes": 45,
                    "language": "en",
                },
            )
        )
        arguments = {
            "confirmation_token": proposal["confirmation_token"],
            "playlist_title": "Account Needs a Channel",
            "user_confirmed": True,
        }
        assert repo.get_pending_playlist(proposal["confirmation_token"]).status == "PENDING"

    if fault is not None:
        provider.inject_fault(fault)

    result = _call(app, tool_name, arguments)
    assert result.isError is True
    assert result.content
    payload = json.loads(result.content[0].text)
    assert set(payload) == {"error_code", "message", "remediation"}
    assert payload["error_code"] == expected_code
    assert payload["message"] == expected_message
    assert isinstance(payload["remediation"], str) and payload["remediation"]
    assert result.structuredContent == {"result": payload}

    response_text = result.content[0].text
    for forbidden in (
        "Traceback",
        "synthetic-secret",
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "/tmp/",
        "/home/",
    ):
        assert forbidden not in response_text
    assert provider.write_calls == []
