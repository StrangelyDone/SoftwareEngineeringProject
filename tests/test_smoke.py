"""Baseline smoke tests for Stage 1 & Stage 2 M0.2 server scaffolding."""

import youtube_mcp
from youtube_mcp import config, db, server
from youtube_mcp.providers import FixtureMockProvider, YouTubeProvider, base, mock


def test_package_version_defined() -> None:
    assert youtube_mcp.__version__ == "0.1.0"


def test_m02_modules_import_cleanly() -> None:
    settings = config.load_settings(env_file=None)
    assert settings.daily_quota_budget == 10_000
    assert settings.soft_warning_threshold_units == 300
    assert db.SCHEMA_STATEMENTS
    assert issubclass(FixtureMockProvider, YouTubeProvider)
    assert base.YouTubeProvider is YouTubeProvider
    assert mock.FixtureMockProvider is FixtureMockProvider
    assert server.app is not None
    assert server.mcp is not None
