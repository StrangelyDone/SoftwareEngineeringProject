"""Offline tests for FastMCP tool registration and dependency wiring."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from youtube_mcp.config import Settings
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.server import configure_logging, create_app

EXPECTED_TOOLS = {
    "find_similar_videos",
    "find_similar_channels",
    "get_recommendations",
    "analyze_user_engagement",
    "propose_playlist",
    "confirm_playlist",
}


def _settings(database_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{database_path}")


def test_app_registers_all_tools_with_valid_draft_2020_12_schemas(
    tmp_path: Path,
) -> None:
    app = create_app(settings=_settings(tmp_path / "tools.db"))
    tools = asyncio.run(app.state.mcp.list_tools())

    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.outputSchema is not None
        Draft202012Validator.check_schema(tool.inputSchema)
        Draft202012Validator.check_schema(tool.outputSchema)


def test_confirm_playlist_schema_requires_explicit_true_and_token(
    tmp_path: Path,
) -> None:
    app = create_app(settings=_settings(tmp_path / "confirmation.db"))
    tools = asyncio.run(app.state.mcp.list_tools())
    confirm_schema = next(
        tool.inputSchema for tool in tools if tool.name == "confirm_playlist"
    )

    assert {"confirmation_token", "playlist_title"} <= set(
        confirm_schema["required"]
    )
    assert confirm_schema["properties"]["user_confirmed"]["default"] is False
    validator = Draft202012Validator(confirm_schema)
    request = {
        "confirmation_token": "fixture-token",
        "user_confirmed": False,
        "playlist_title": "Requested playlist",
    }
    assert not list(validator.iter_errors(request))


def test_app_injects_repository_and_provider_into_services(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "injected.db")
    provider = FixtureMockProvider()
    app = create_app(
        settings=_settings(tmp_path / "unused.db"),
        provider=provider,
        repository=repository,
    )

    assert app.state.services.repository is repository
    assert app.state.services.provider is provider
    assert app.state.services.quota_guard.repo is repository
    assert app.state.services.similarity.provider is provider
    assert app.state.services.recommendations.provider is provider
    assert app.state.services.analytics.provider is provider
    assert app.state.services.playlists.provider is provider

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert repository.db_path.exists()
    assert not (tmp_path / "unused.db").exists()


def test_offline_app_defaults_to_fixture_provider(tmp_path: Path) -> None:
    app = create_app(settings=_settings(tmp_path / "offline.db"))

    assert isinstance(app.state.provider, FixtureMockProvider)


def test_configure_logging_routes_root_handler_only_to_stderr() -> None:
    configure_logging()

    root_logger = logging.getLogger()
    assert root_logger.handlers
    assert all(
        isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr
        for handler in root_logger.handlers
    )
