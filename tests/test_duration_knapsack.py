"""Offline unit tests for ISO-8601 duration parsing, knapsack packing, and FR-5 gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from youtube_mcp.exceptions import (
    ConfirmationRequiredError,
    InvalidVideoIdentifierError,
    QuotaBudgetExceededError,
    YouTubeSignupRequiredError,
)
from youtube_mcp.models import VideoMetadata
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.quota_guard import QuotaGuard
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.services.duration import parse_iso8601_duration, try_parse_iso8601_duration
from youtube_mcp.services.playlist import PlaylistProposalRequest, PlaylistService

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class WriteSpyMockProvider(FixtureMockProvider):
    """Spy wrapper around FixtureMockProvider counting Phase 1 / Phase 2 write calls."""

    def __init__(self, fixtures_dir: Path, fault_mode: str | None = None) -> None:
        super().__init__(fixtures_dir=fixtures_dir, fault_mode=fault_mode)
        self.write_calls: list[tuple[str, str]] = []

    def create_playlist(self, title: str, description: str = "", privacy_status: str = "private"):
        self.write_calls.append(("playlists.insert", title))
        return super().create_playlist(title=title, description=description, privacy_status=privacy_status)

    def add_playlist_item(self, playlist_id: str, video_id: str):
        self.write_calls.append(("playlistItems.insert", video_id))
        return super().add_playlist_item(playlist_id=playlist_id, video_id=video_id)


def _make_playlist_service(
    tmp_path: Path,
    *,
    daily_budget: int = 10_000,
    fault_mode: str | None = None,
) -> tuple[PlaylistService, WriteSpyMockProvider, SQLiteRepository]:
    repo = SQLiteRepository(tmp_path / "playlist.db")
    repo.initialize_schema()
    guard = QuotaGuard(repo, daily_quota_budget=daily_budget)
    provider = WriteSpyMockProvider(FIXTURES, fault_mode=fault_mode)
    service = PlaylistService(provider=provider, quota_guard=guard, repo=repo)
    return service, provider, repo


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PT1H2M3S", 3723),
        ("PT15M33S", 933),
        ("PT45S", 45),
        ("PT0S", 0),
        ("PT2H", 7200),
        ("P1DT2H", 93600),
    ],
)
def test_parse_iso8601_duration_valid(raw: str, expected: int) -> None:
    assert parse_iso8601_duration(raw) == expected
    assert try_parse_iso8601_duration(raw) == expected


@pytest.mark.parametrize(
    "bad_raw",
    [
        "",
        "   ",
        "P",
        "PT",
        "P1DT",
        "-PT5M",
        "PT-5M",
        "not-an-iso-duration",
        "15:30",
        "PT1.5M",
        "PT5M30",
    ],
)
def test_parse_iso8601_duration_rejects_malformed(bad_raw: str) -> None:
    with pytest.raises(ValueError):
        parse_iso8601_duration(bad_raw)
    assert try_parse_iso8601_duration(bad_raw) is None


def test_filter_candidates_enforces_duration_language_and_excludes_malformed() -> None:
    candidates = [
        VideoMetadata(
            video_id="vidOK_EN_10M",
            title="Good English",
            duration_iso="PT10M00S",
            default_language="en",
        ),
        VideoMetadata(
            video_id="vidOK_EN_US_",
            title="Good US English Audio",
            duration_iso="PT8M00S",
            default_audio_language="en-US",
        ),
        VideoMetadata(
            video_id="vidTOO_LONG_",
            title="Too Long",
            duration_iso="PT20M00S",
            default_language="en",
        ),
        VideoMetadata(
            video_id="vidWRONG_LNG",
            title="Spanish Video",
            duration_iso="PT5M00S",
            default_language="es",
        ),
        VideoMetadata(
            video_id="vidBAD_DURAT",
            title="Malformed",
            duration_iso="not-an-iso-duration",
            default_language="en",
        ),
        VideoMetadata(
            video_id="vidZERO_DUR_",
            title="Zero",
            duration_iso="PT0S",
            default_language="en",
        ),
    ]

    filtered = PlaylistService.filter_candidates(
        candidates, max_video_seconds=600, language="en"
    )
    assert [video.video_id for video, _ in filtered] == ["vidOK_EN_10M", "vidOK_EN_US_"]

    with pytest.raises(InvalidVideoIdentifierError):
        PlaylistService.filter_candidates(candidates, language="english")


def test_knapsack_optimality_and_exact_total_duration_boundary() -> None:
    # Greedy highest-score-first picks v1 (1000s, score 0.90) leaving 800s unused;
    # Optimal 0/1 knapsack picks v2 + v3 (900 + 900 = 1800s exact boundary, score 1.60).
    v1 = VideoMetadata(video_id="vid1", title="Big One", duration_iso="PT16M40S")
    v2 = VideoMetadata(video_id="vid2", title="Half A", duration_iso="PT15M00S")
    v3 = VideoMetadata(video_id="vid3", title="Half B", duration_iso="PT15M00S")

    packed = PlaylistService.pack_videos_knapsack(
        [(v1, 1000, 0.90), (v2, 900, 0.80), (v3, 900, 0.80)],
        max_total_seconds=1800,
    )
    assert sorted(v.video_id for v, _, _ in packed) == ["vid2", "vid3"]
    assert sum(dur for _, dur, _ in packed) == 1800
    assert sum(score for _, _, score in packed) == pytest.approx(1.60)


def test_phase1_propose_playlist_zero_writes_and_persists_draft(tmp_path: Path) -> None:
    service, provider, repo = _make_playlist_service(tmp_path)
    t0 = datetime(2026, 11, 28, 12, 0, 0, tzinfo=UTC)

    proposal = service.propose_playlist(
        PlaylistProposalRequest(
            topic="python",
            max_total_duration_minutes=55,
            max_video_duration_minutes=45,
            language="en",
        ),
        now=t0,
    )

    assert provider.write_calls == []
    assert proposal.requires_explicit_user_confirmation is True
    assert proposal.total_duration_seconds <= 55 * 60
    assert len(proposal.proposed_videos) >= 1
    assert all(item.untrusted_metadata is True for item in proposal.proposed_videos)
    assert proposal.estimated_write_quota_cost == 50 + (50 * len(proposal.proposed_videos))

    stored = repo.get_pending_playlist(proposal.confirmation_token)
    assert stored is not None
    assert stored.status == "PENDING"


def test_phase2_confirmation_gate_rejects_unconfirmed_expired_and_replayed(
    tmp_path: Path,
) -> None:
    service, provider, repo = _make_playlist_service(tmp_path)
    t0 = datetime(2026, 11, 28, 12, 0, 0, tzinfo=UTC)

    proposal = service.propose_playlist(
        PlaylistProposalRequest(
            topic="distributed systems",
            max_total_duration_minutes=30,
            max_video_duration_minutes=20,
            language="en",
        ),
        now=t0,
    )

    # 1. user_confirmed=False must fail with 0 writes
    with pytest.raises(ConfirmationRequiredError):
        service.confirm_playlist(
            confirmation_token=proposal.confirmation_token,
            user_confirmed=False,
            playlist_title="Systems Playlist",
            now=t0 + timedelta(minutes=1),
        )
    assert provider.write_calls == []

    # 2. Missing / unknown token must fail with 0 writes
    with pytest.raises(ConfirmationRequiredError):
        service.confirm_playlist(
            confirmation_token="unknown-token",
            user_confirmed=True,
            playlist_title="Systems Playlist",
            now=t0 + timedelta(minutes=1),
        )
    assert provider.write_calls == []

    # 3. Valid confirmation executes playlists.insert + N x playlistItems.insert
    created = service.confirm_playlist(
        confirmation_token=proposal.confirmation_token,
        user_confirmed=True,
        playlist_title="Systems Playlist",
        now=t0 + timedelta(minutes=2),
    )
    assert created.status == "COMPLETED"
    assert created.items_added == len(proposal.proposed_videos)
    assert created.quota_used == 50 + (50 * created.items_added)
    assert len(provider.write_calls) == 1 + created.items_added

    # 4. Replay of the same token must fail with 0 additional writes
    write_count_after_success = len(provider.write_calls)
    with pytest.raises(ConfirmationRequiredError):
        service.confirm_playlist(
            confirmation_token=proposal.confirmation_token,
            user_confirmed=True,
            playlist_title="Replay Attempt",
            now=t0 + timedelta(minutes=3),
        )
    assert len(provider.write_calls) == write_count_after_success

    # 5. Expired token (>15m) must transition to EXPIRED and reject
    proposal_exp = service.propose_playlist(
        PlaylistProposalRequest(
            topic="python",
            max_total_duration_minutes=30,
            max_video_duration_minutes=20,
            language="en",
        ),
        now=t0,
    )
    with pytest.raises(ConfirmationRequiredError):
        service.confirm_playlist(
            confirmation_token=proposal_exp.confirmation_token,
            user_confirmed=True,
            playlist_title="Too Late",
            now=t0 + timedelta(minutes=16),
        )
    expired_draft = repo.get_pending_playlist(proposal_exp.confirmation_token)
    assert expired_draft is not None
    assert expired_draft.status == "EXPIRED"


def test_phase2_preflight_quota_blocks_writes_before_partial_creation(tmp_path: Path) -> None:
    service, provider, repo = _make_playlist_service(tmp_path, daily_budget=10_000)
    t0 = datetime(2026, 11, 28, 12, 0, 0, tzinfo=UTC)

    candidates = [
        VideoMetadata(
            video_id="vidDS000001",
            title="Distributed Systems",
            duration_iso="PT10M00S",
            default_language="en",
        ),
        VideoMetadata(
            video_id="vidSQL00003",
            title="SQLite WAL",
            duration_iso="PT10M00S",
            default_language="en",
        ),
    ]
    proposal = service.propose_playlist(
        PlaylistProposalRequest(topic="systems", max_total_duration_minutes=30, language="en"),
        candidates=candidates,
        now=t0,
    )
    assert proposal.estimated_write_quota_cost == 150  # 50 + 50 * 2

    # Leave only 100 units remaining (< 150 needed)
    repo.record_quota_usage("search.list", 9_900, "exhaust", now=t0)

    with pytest.raises(QuotaBudgetExceededError):
        service.confirm_playlist(
            confirmation_token=proposal.confirmation_token,
            user_confirmed=True,
            playlist_title="Blocked Playlist",
            now=t0 + timedelta(minutes=1),
        )

    # Critical TQ-6 / REQ-FR5-6 invariant: zero playlists.insert / playlistItems.insert called
    assert provider.write_calls == []


def test_phase2_handles_youtube_signup_required_and_marks_failed(tmp_path: Path) -> None:
    service, provider, repo = _make_playlist_service(tmp_path)
    t0 = datetime(2026, 11, 28, 12, 0, 0, tzinfo=UTC)

    candidates = [
        VideoMetadata(
            video_id="vidDS000001",
            title="Distributed Systems",
            duration_iso="PT10M00S",
            default_language="en",
        )
    ]
    proposal = service.propose_playlist(
        PlaylistProposalRequest(topic="systems", max_total_duration_minutes=20, language="en"),
        candidates=candidates,
        now=t0,
    )

    provider.inject_fault("youtube_signup_required")
    with pytest.raises(YouTubeSignupRequiredError):
        service.confirm_playlist(
            confirmation_token=proposal.confirmation_token,
            user_confirmed=True,
            playlist_title="No Channel Account",
            now=t0 + timedelta(minutes=1),
        )

    failed_draft = repo.get_pending_playlist(proposal.confirmation_token)
    assert failed_draft is not None
    assert failed_draft.status == "FAILED"
