"""Offline integration coverage for the M1-M3 service stack (`TQ-2`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from youtube_mcp.exceptions import QuotaBudgetExceededError
from youtube_mcp.models import ChannelMetadata, VideoMetadata
from youtube_mcp.providers.mock import FixtureMockProvider
from youtube_mcp.quota_guard import QuotaGuard
from youtube_mcp.repository import SQLiteRepository
from youtube_mcp.services.analytics import AnalyticsService
from youtube_mcp.services.playlist import PlaylistProposalRequest, PlaylistService
from youtube_mcp.services.recommendation import RecommendationService
from youtube_mcp.services.similarity import SimilarityService

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VALID_CHANNEL_ID = "UC_x5XG1OV2P6uZZ5FSM9Ttw"


class CountingFixtureMockProvider(FixtureMockProvider):
    """Fixture provider with observable offline API and playlist-write calls."""

    def __init__(self) -> None:
        super().__init__(FIXTURES)
        self.calls: list[str] = []
        self.write_calls: list[str] = []

    def get_videos(self, video_ids: list[str]) -> list[VideoMetadata]:
        self.calls.append("videos.list")
        return super().get_videos(video_ids)

    def get_channels(
        self,
        channel_ids: list[str] | None = None,
        handle: str | None = None,
    ) -> list[ChannelMetadata]:
        self.calls.append("channels.list")
        if channel_ids == [VALID_CHANNEL_ID]:
            channel = super().get_channels(channel_ids=["UCsynthetic001"])[0]
            return [channel.model_copy(update={"channel_id": VALID_CHANNEL_ID})]
        return super().get_channels(channel_ids=channel_ids, handle=handle)

    def search_videos(
        self,
        query: str,
        max_results: int = 25,
        page_token: str | None = None,
        language: str | None = None,
    ):
        self.calls.append("search.list")
        return super().search_videos(
            query,
            max_results=max_results,
            page_token=page_token,
            language=language,
        )

    def get_user_likes(self, max_results: int = 50) -> list[VideoMetadata]:
        self.calls.append("videos.list:likes")
        return super().get_user_likes(max_results=max_results)

    def get_user_subscriptions(self, max_results: int = 50) -> list[ChannelMetadata]:
        self.calls.append("subscriptions.list")
        return super().get_user_subscriptions(max_results=max_results)

    def get_user_playlists(self, max_results: int = 50):
        self.calls.append("playlists.list")
        return super().get_user_playlists(max_results=max_results)

    def get_playlist_items(self, playlist_id: str, max_results: int = 50) -> list[str]:
        self.calls.append("playlistItems.list")
        return super().get_playlist_items(playlist_id, max_results=max_results)

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ):
        self.write_calls.append("playlists.insert")
        return super().create_playlist(title, description, privacy_status)

    def add_playlist_item(self, playlist_id: str, video_id: str):
        self.write_calls.append("playlistItems.insert")
        return super().add_playlist_item(playlist_id, video_id)


def _stack(
    tmp_path: Path,
    *,
    provider: CountingFixtureMockProvider | None = None,
    daily_budget: int = 10_000,
) -> tuple[
    SQLiteRepository,
    CountingFixtureMockProvider,
    QuotaGuard,
    SimilarityService,
    RecommendationService,
    AnalyticsService,
    PlaylistService,
]:
    repo = SQLiteRepository(tmp_path / "integration.db")
    repo.initialize_schema()
    fixture_provider = provider or CountingFixtureMockProvider()
    guard = QuotaGuard(repo, daily_quota_budget=daily_budget)
    similarity = SimilarityService(
        provider=fixture_provider,
        quota_guard=guard,
        repo=repo,
    )
    return (
        repo,
        fixture_provider,
        guard,
        similarity,
        RecommendationService(
            provider=fixture_provider,
            quota_guard=guard,
            repo=repo,
            similarity=similarity,
        ),
        AnalyticsService(provider=fixture_provider, quota_guard=guard, repo=repo),
        PlaylistService(provider=fixture_provider, quota_guard=guard, repo=repo),
    )


def test_similarity_services_integrate_provider_cache_and_quota(tmp_path: Path) -> None:
    repo, provider, _, similarity, *_ = _stack(tmp_path)

    videos = similarity.find_similar_videos("vidPY000002", limit=5)
    assert videos.quota_used > 0
    assert "search.list" in provider.calls
    assert repo.get_used_quota() == videos.quota_used
    cached_videos = repo.get_cached_videos(
        [videos.seed_video_id, *(item.video_id for item in videos.results)]
    )
    assert videos.seed_video_id in cached_videos
    assert len(cached_videos) > 1

    calls_after_video_miss = len(provider.calls)
    cached_candidates = [
        VideoMetadata.model_validate(payload) for payload in cached_videos.values()
    ]
    cached_video_result = similarity.find_similar_videos(
        videos.seed_video_id,
        candidates=cached_candidates,
        limit=5,
    )
    assert cached_video_result.quota_used == 0
    assert len(provider.calls) == calls_after_video_miss

    candidate_channels = [
        ChannelMetadata(
            channel_id="UCsynthetic002",
            title="Python Studio",
            handle="@python-studio",
            keywords=["python", "systems"],
            topic_categories=["Technology"],
        ),
        ChannelMetadata(
            channel_id="UCsynthetic004",
            title="Test Kitchen",
            handle="@test-kitchen",
            keywords=["cooking"],
            topic_categories=["Food"],
        ),
    ]
    upload_map = {
        VALID_CHANNEL_ID: [],
        "UCsynthetic002": [],
        "UCsynthetic004": [],
    }
    channels = similarity.find_similar_channels(
        VALID_CHANNEL_ID,
        candidates=candidate_channels,
        channel_videos=upload_map,
    )
    assert channels.quota_used == 1
    assert channels.seed_channel_id == VALID_CHANNEL_ID
    assert repo.get_cached_channels([channels.seed_channel_id])
    assert repo.get_used_quota() == videos.quota_used + channels.quota_used

    calls_after_channel_miss = len(provider.calls)
    cached_channels = similarity.find_similar_channels(
        VALID_CHANNEL_ID,
        candidates=candidate_channels,
        channel_videos=upload_map,
    )
    assert cached_channels.quota_used == 0
    assert len(provider.calls) == calls_after_channel_miss
    assert repo.get_used_quota() == videos.quota_used + channels.quota_used


def test_quota_cutoff_blocks_provider_before_cache_miss_fetch(tmp_path: Path) -> None:
    repo, provider, _, similarity, *_ = _stack(tmp_path, daily_budget=100)

    with pytest.raises(QuotaBudgetExceededError):
        similarity.find_similar_videos("vidPY000002")

    assert provider.calls == []
    assert repo.get_used_quota() == 0


def test_recommendations_and_engagement_integrate_fixture_library(tmp_path: Path) -> None:
    repo, _, _, _, recommendations, analytics, _ = _stack(tmp_path)

    quota_before_recommendations = repo.get_used_quota()
    recs = recommendations.recommend_for_user(limit=5)
    assert recs.recommendations
    assert all(item.video_id not in {"vidDS000001", "vidPY000002"} for item in recs.recommendations)
    assert recs.recommendations[0].explanation
    assert recs.quota_used > 0
    quota_after_recommendations = repo.get_used_quota()
    assert quota_after_recommendations > quota_before_recommendations
    assert recs.remaining_daily_quota == 10_000 - quota_after_recommendations

    quota_before_analytics = repo.get_used_quota()
    report = analytics.analyze_engagement(granularity="quarter")
    assert report.liked_video_count == 4
    assert report.subscription_count == 3
    assert report.playlist_count == 2
    assert report.unique_video_count == 7
    assert report.top_channels
    assert report.duration_preferences.valid_video_count > 0
    assert report.quota_used > 0
    quota_after_analytics = repo.get_used_quota()
    assert quota_after_analytics > quota_before_analytics
    assert report.remaining_daily_quota == 10_000 - quota_after_analytics


def test_playlist_proposal_confirmation_completes_and_accounts_writes(
    tmp_path: Path,
) -> None:
    repo, provider, _, _, _, _, playlists = _stack(tmp_path)

    proposal = playlists.propose_playlist(
        PlaylistProposalRequest(
            topic="python",
            max_total_duration_minutes=60,
            max_video_duration_minutes=45,
            language="en",
        )
    )

    assert proposal.proposed_videos
    assert proposal.requires_explicit_user_confirmation is True
    assert provider.write_calls == []
    draft = repo.get_pending_playlist(proposal.confirmation_token)
    assert draft is not None
    assert draft.status == "PENDING"
    quota_before_confirmation = repo.get_used_quota()

    created = playlists.confirm_playlist(
        confirmation_token=proposal.confirmation_token,
        user_confirmed=True,
        playlist_title="Offline Python Playlist",
    )

    expected_write_cost = 50 + 50 * len(proposal.proposed_videos)
    assert created.status == "COMPLETED"
    assert created.items_added == len(proposal.proposed_videos)
    assert created.quota_used == expected_write_cost
    assert repo.get_used_quota() - quota_before_confirmation == expected_write_cost
    assert provider.write_calls == [
        "playlists.insert",
        *("playlistItems.insert" for _ in proposal.proposed_videos),
    ]
    completed = repo.get_pending_playlist(proposal.confirmation_token)
    assert completed is not None
    assert completed.status == "COMPLETED"
