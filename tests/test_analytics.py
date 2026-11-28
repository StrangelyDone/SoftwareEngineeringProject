"""Offline unit tests for AnalyticsService (FR-4) and RecommendationService (FR-3)."""

from __future__ import annotations

from pathlib import Path

from youtube_mcp.models import ChannelMetadata, PlaylistSummary, VideoMetadata
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.quota_guard import QuotaGuard
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.services.analytics import AnalyticsService
from youtube_mcp.services.recommendation import RecommendationService

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _sample_videos() -> list[VideoMetadata]:
    return [
        VideoMetadata(
            video_id="vidA0000001",
            title="Short Intro",
            channel_id="UC_CH1",
            channel_title="Systems Lab",
            category_id="28",
            duration_iso="PT4M59S",  # 299s -> Short (<300)
            published_at="2026-01-10T10:00:00Z",
        ),
        VideoMetadata(
            video_id="vidA0000002",
            title="Medium Boundary",
            channel_id="UC_CH1",
            channel_title="Systems Lab",
            category_id="28",
            duration_iso="PT5M00S",  # 300s -> Medium (300..1199)
            published_at="2026-01-20T10:00:00Z",
        ),
        VideoMetadata(
            video_id="vidA0000003",
            title="Long Boundary",
            channel_id="UC_CH2",
            channel_title="Python Studio",
            category_id="27",
            duration_iso="PT20M00S",  # 1200s -> Long (1200..3600)
            published_at="2026-02-05T10:00:00Z",
        ),
        VideoMetadata(
            video_id="vidA0000004",
            title="Exact Hour Long",
            channel_id="UC_CH2",
            channel_title="Python Studio",
            category_id="27",
            duration_iso="PT1H00M00S",  # 3600s -> Long (1200..3600)
            published_at="2026-02-15T10:00:00Z",
        ),
        VideoMetadata(
            video_id="vidA0000005",
            title="Deep Dive Talk",
            channel_id="UC_CH1",
            channel_title="Systems Lab",
            category_id="28",
            duration_iso="PT1H00M01S",  # 3601s -> Deep-Dive (>3600)
            published_at="2026-02-22T10:00:00Z",
        ),
        VideoMetadata(
            video_id="vidA0000006",
            title="Malformed Duration Excluded",
            channel_id="UC_CH3",
            channel_title="Broken Channel",
            category_id=None,
            duration_iso="not-an-iso-duration",
            published_at="2026-02-25T10:00:00Z",
        ),
    ]


def test_analytics_distributions_trends_and_duration_buckets() -> None:
    svc = AnalyticsService()
    videos = _sample_videos()
    report = svc.build_report(
        liked_videos=videos[:4],
        playlist_videos=videos[3:],  # vidA0000004 overlaps and must be deduped
        subscriptions=[ChannelMetadata(channel_id="UC_CH1", title="Systems Lab")],
        playlists=[PlaylistSummary(playlist_id="PL1", title="Core")],
        granularity="month",
        period_a_start="2026-01-01",
        period_a_end="2026-01-31",
        period_b_start="2026-02-01",
        period_b_end="2026-02-28",
    )

    assert report.unique_video_count == 6
    assert report.subscription_count == 1
    assert report.playlist_count == 1
    assert report.missing_category_count == 1
    assert report.timestamp_source == "video.snippet.publishedAt"

    # Top channels across 6 unique videos: UC_CH1=3 (50%), UC_CH2=2 (33.33%), UC_CH3=1 (16.67%)
    assert report.top_channels[0].channel_id == "UC_CH1"
    assert report.top_channels[0].count == 3
    assert report.top_channels[0].percentage == 50.0

    # Top categories across 5 categorized videos: "28"=3 (60%), "27"=2 (40%)
    assert report.top_categories[0].category_id == "28"
    assert report.top_categories[0].count == 3
    assert report.top_categories[0].percentage == 60.0

    # Monthly trends
    assert [(t.period, t.video_count, t.top_category_id) for t in report.trends_over_time] == [
        ("2026-01", 2, "28"),
        ("2026-02", 4, "27"),
    ]

    # Duration stats & exact boundary buckets: 299, 300, 1200, 3600, 3601 (1 malformed excluded)
    dp = report.duration_preferences
    assert dp.valid_video_count == 5
    assert dp.invalid_duration_count == 1
    assert dp.min_seconds == 299
    assert dp.max_seconds == 3601
    assert dp.median_seconds == 1200.0
    assert dp.buckets.short_lt_5m == 1
    assert dp.buckets.medium_5m_20m == 1
    assert dp.buckets.long_20m_60m == 2
    assert dp.buckets.deep_dive_gt_60m == 1

    # Period-over-period comparison: Jan (2) vs Feb (4) -> +100%
    assert report.period_comparison is not None
    assert report.period_comparison.period_a.video_count == 2
    assert report.period_comparison.period_b.video_count == 4
    assert report.period_comparison.volume_absolute_delta == 2
    assert report.period_comparison.volume_percentage_delta == 100.0


def test_analytics_period_comparison_zero_baseline_and_empty_library_tq4() -> None:
    svc = AnalyticsService()

    # Empty library zero-state must not raise
    empty_report = svc.build_report()
    assert empty_report.unique_video_count == 0
    assert empty_report.top_channels == []
    assert empty_report.top_categories == []
    assert empty_report.trends_over_time == []
    assert empty_report.duration_preferences.valid_video_count == 0
    assert empty_report.duration_preferences.mean_seconds == 0.0
    assert empty_report.period_comparison is not None
    assert empty_report.period_comparison.volume_percentage_delta is None
    assert "N/A" in empty_report.period_comparison.volume_percentage_delta_display

    # Zero baseline in Period A for a category present only in Period B
    partial_report = svc.build_report(
        liked_videos=[
            VideoMetadata(
                video_id="vidFEB00001",
                title="New Topic",
                channel_id="UC_NEW",
                category_id="28",
                duration_iso="PT10M00S",
                published_at="2026-02-10T10:00:00Z",
            )
        ],
        period_a_start="2026-01-01",
        period_a_end="2026-01-31",
        period_b_start="2026-02-01",
        period_b_end="2026-02-28",
    )
    assert partial_report.period_comparison is not None
    assert partial_report.period_comparison.volume_absolute_delta == 1
    assert partial_report.period_comparison.volume_percentage_delta is None
    assert "N/A" in partial_report.period_comparison.volume_percentage_delta_display
    cat_delta = partial_report.period_comparison.category_deltas[0]
    assert cat_delta.period_a_count == 0
    assert cat_delta.period_b_count == 1
    assert cat_delta.percentage_delta is None


def test_analytics_service_with_provider_and_quarterly_trends(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "analytics.db")
    repo.initialize_schema()
    guard = QuotaGuard(repo)
    provider = FixtureMockProvider(FIXTURES)
    svc = AnalyticsService(provider=provider, quota_guard=guard, repo=repo)

    report = svc.analyze_engagement(granularity="quarter")
    assert report.liked_video_count == 4
    assert report.subscription_count == 3
    assert report.playlist_count == 2
    assert report.unique_video_count == 7
    assert report.quota_used > 0
    assert [t.period for t in report.trends_over_time] == ["2026-Q1"]


def test_recommendation_service_excludes_seen_and_builds_rationales(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "rec.db")
    repo.initialize_schema()
    guard = QuotaGuard(repo)
    provider = FixtureMockProvider(FIXTURES)
    svc = RecommendationService(provider=provider, quota_guard=guard, repo=repo)

    # vidDS000001, vidPY000002, vidSQL00003, vidPY000012 are liked;
    # vidES000004, vidDE000005, vidTAG000008 are in PLsynthetic002.
    # Unseen fixture videos include vidDS000013 (Systems Lab, subscribed) & vidCOOK0006.
    res = svc.recommend_for_user(limit=5)
    returned_ids = {item.video_id for item in res.recommendations}
    assert "vidDS000001" not in returned_ids
    assert "vidPY000002" not in returned_ids
    assert "vidES000004" not in returned_ids
    assert "vidDS000013" in returned_ids

    top_item = res.recommendations[0]
    assert top_item.untrusted_metadata is True
    assert top_item.explanation.startswith("Recommended because it ")

    # focus_topic narrows unseen candidates
    focused = svc.recommend_for_user(limit=5, focus_topic="consensus")
    assert [item.video_id for item in focused.recommendations] == ["vidDS000013"]
    assert "consensus" in focused.recommendations[0].explanation.lower()
