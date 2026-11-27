"""Offline unit tests for SQLiteRepository in youtube_mcp.repository (M1.1 / M1.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from youtube_mcp.db import (
    SQLiteRepository as BaseSQLiteRepository,
)
from youtube_mcp.db import (
    get_remaining_quota,
)
from youtube_mcp.exceptions import ConfirmationRequiredError
from youtube_mcp.repository import SQLiteRepository


def _make_repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "test.db")
    repo.initialize_schema()
    return repo


def test_wal_health_and_db_compatibility(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    assert isinstance(repo, BaseSQLiteRepository)

    health = repo.check_wal_health()
    assert health["journal_mode"] == "wal"
    assert health["daily_quota_budget"] == 10_000
    assert health["used_today"] == 0
    assert health["remaining_quota"] == 10_000


def test_cached_videos_24h_ttl_and_atomic_overwrite(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    t0 = datetime(2026, 11, 27, 10, 0, 0, tzinfo=UTC)

    repo.upsert_cached_videos({"vid_1": {"title": "Initial Title"}}, now=t0)

    hits = repo.get_cached_videos(
        ["vid_1", "missing_vid"],
        now=t0 + timedelta(hours=23),
    )
    assert hits == {"vid_1": {"title": "Initial Title"}}

    expired = repo.get_cached_videos(
        ["vid_1"],
        now=t0 + timedelta(hours=24, seconds=1),
    )
    assert expired == {}

    t1 = t0 + timedelta(hours=25)
    repo.upsert_cached_videos({"vid_1": {"title": "Refreshed Title"}}, now=t1)
    refreshed = repo.get_cached_videos(["vid_1"], now=t1 + timedelta(minutes=5))
    assert refreshed == {"vid_1": {"title": "Refreshed Title"}}


def test_cached_channels_7d_ttl(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    t0 = datetime(2026, 11, 27, 10, 0, 0, tzinfo=UTC)

    repo.upsert_cached_channels({"UC_123": {"title": "Systems Channel"}}, now=t0)

    hits = repo.get_cached_channels(["UC_123"], now=t0 + timedelta(days=6))
    assert hits == {"UC_123": {"title": "Systems Channel"}}

    expired = repo.get_cached_channels(
        ["UC_123"],
        now=t0 + timedelta(days=7, seconds=1),
    )
    assert expired == {}


def test_pending_playlist_one_way_completion_and_no_replay(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    t0 = datetime(2026, 11, 27, 10, 0, 0, tzinfo=UTC)

    draft = repo.create_pending_playlist(
        topic="linux networking",
        constraints={"max_total_duration_minutes": 60, "language": "en"},
        selected_video_ids=["v1", "v2", "v3"],
        total_duration_seconds=1800,
        now=t0,
    )
    assert draft.status == "PENDING"
    assert draft.estimated_quota_cost == 200  # 50 + 50 * 3

    completed = repo.transition_pending_playlist(
        draft.confirmation_token,
        "COMPLETED",
        now=t0 + timedelta(minutes=5),
    )
    assert completed.status == "COMPLETED"

    with pytest.raises(ConfirmationRequiredError):
        repo.transition_pending_playlist(
            draft.confirmation_token,
            "COMPLETED",
            now=t0 + timedelta(minutes=6),
        )


def test_pending_playlist_auto_expires_after_15_minutes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    t0 = datetime(2026, 11, 27, 10, 0, 0, tzinfo=UTC)

    draft = repo.create_pending_playlist(
        topic="python async",
        constraints={"max_total_duration_minutes": 30},
        selected_video_ids=["v1"],
        total_duration_seconds=600,
        now=t0,
    )

    with pytest.raises(ConfirmationRequiredError):
        repo.transition_pending_playlist(
            draft.confirmation_token,
            "COMPLETED",
            now=t0 + timedelta(minutes=16),
        )

    stored = repo.get_pending_playlist(draft.confirmation_token)
    assert stored is not None
    assert stored.status == "EXPIRED"


def test_quota_ledger_sums_by_utc_date_and_rolls_over(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    repo.record_quota_usage("search.list", 100, "FR-1", date_utc="2026-11-26")
    repo.record_quota_usage("videos.list", 2, "FR-1", date_utc="2026-11-26")
    repo.record_quota_usage("playlists.insert", 50, "FR-5", date_utc="2026-11-27")

    assert repo.get_used_quota(date_utc="2026-11-26") == 102
    assert repo.get_used_quota(date_utc="2026-11-27") == 50
    assert repo.get_used_quota(date_utc="2026-11-28") == 0
    assert (
        get_remaining_quota(db_path=repo.db_path, date_utc="2026-11-27")
        == 9_950
    )
