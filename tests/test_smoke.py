"""Baseline smoke test for Stage 1 CI skeleton."""

import youtube_mcp


def test_package_version_defined() -> None:
    assert youtube_mcp.__version__ == "0.1.0"