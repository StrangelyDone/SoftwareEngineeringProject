"""Offline unit tests for QuotaGuard (M1.2 / M1.3 / TQ-6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from youtube_mcp.exceptions import QuotaBudgetExceededError
from youtube_mcp.quota_guard import QuotaGuard, QuotaOperation
from youtube_mcp.repository import SQLiteRepository


class SpyProvider:
    """Minimal spy verifying zero provider calls happen on pre-flight rejection."""

    def __init__(self) -> None:
        self.call_count = 0

    def search_videos(self) -> list[str]:
        self.call_count += 1
        return ["vid_1"]


def _make_repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "quota.db")
    repo.initialize_schema()
    return repo


def test_preflight_blocks_before_provider_call(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    guard = QuotaGuard(repo, daily_quota_budget=10_000)
    spy = SpyProvider()

    repo.record_quota_usage("search.list", 9_950, "seed", date_utc="2026-11-27")

    cost = guard.estimate_cost([QuotaOperation("search.list", count=1)])
    assert cost == 100

    with pytest.raises(QuotaBudgetExceededError):
        guard.preflight_check(cost, "FR-1:find_similar_videos", date_utc="2026-11-27")
        spy.search_videos()

    assert spy.call_count == 0


def test_playlist_write_cost_blocks_partial_creation(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    guard = QuotaGuard(repo, daily_quota_budget=10_000)

    repo.record_quota_usage("search.list", 9_750, "seed", date_utc="2026-11-27")
    write_cost = guard.estimate_playlist_write_cost(video_count=5)
    assert write_cost == 300

    with pytest.raises(QuotaBudgetExceededError):
        guard.preflight_check(
            write_cost,
            "FR-5:confirm_playlist",
            date_utc="2026-11-27",
        )


def test_soft_warning_threshold_boundary(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    guard = QuotaGuard(repo, daily_quota_budget=10_000, soft_warning_threshold=300)

    ok_decision = guard.preflight_check(200, "FR-1:discovery", date_utc="2026-11-27")
    assert ok_decision.allowed is True
    assert ok_decision.quota_warning is None
    assert ok_decision.remaining_after == 9_800

    warn_decision = guard.preflight_check(
        350,
        "FR-5:confirm_playlist",
        date_utc="2026-11-27",
    )
    assert warn_decision.allowed is True
    assert warn_decision.quota_warning is not None
    assert "350" in warn_decision.quota_warning


def test_estimate_cost_skips_cached_and_caps_search_pages(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    guard = QuotaGuard(repo, max_search_pages=2)

    cost = guard.estimate_cost([
        QuotaOperation("videos.list", count=1, cached=True),
        QuotaOperation("search.list", count=2, cached=False),
        QuotaOperation("videos.list", count=1, cached=False),
    ])
    assert cost == 201

    with pytest.raises(ValueError, match="max_search_pages"):
        guard.estimate_cost([QuotaOperation("search.list", count=3, cached=False)])


def test_mark_quota_exhausted_drains_remaining_budget(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    guard = QuotaGuard(repo, daily_quota_budget=10_000)

    guard.commit_usage("videos.list", 5, "FR-1", date_utc="2026-11-27")
    assert guard.remaining_budget(date_utc="2026-11-27") == 9_995

    guard.mark_quota_exhausted(date_utc="2026-11-27")
    assert guard.remaining_budget(date_utc="2026-11-27") == 0

    with pytest.raises(QuotaBudgetExceededError):
        guard.preflight_check(1, "FR-1:post_403", date_utc="2026-11-27")
